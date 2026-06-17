#!/usr/bin/env python3
"""Eval signal G6 — disambiguation (deterministic core + optional-LLM suggestion).

Deterministic core
------------------
Identifies overlapping concepts that are merge-or-split candidates based on:

1. **Shared names / aliases** — two artifacts share the same title or alias
   string (case-folded).  They likely duplicate the same concept and should be
   merged.
2. **Shared linking artifacts** — two artifacts are both referenced from a
   third artifact's ``linked_concepts`` field.  Frequent co-citation in the
   same neighbourhood is a light structural signal.
3. **Structural tag overlap** — two knowledge-note artifacts share the majority
   of their tags, suggesting they may cover the same topic from two angles
   (split candidate) or be genuine duplicates (merge candidate).

The deterministic pass produces ``"candidate"`` findings that require no
model backend.

Optional-LLM suggestion
------------------------
When ``tools.llm_provider.get_provider()`` returns an enabled provider the
signal asks the model to classify each candidate as ``merge`` or ``split`` and
attaches the suggestion as a second finding.  When no backend is configured
the LLM step is silently skipped — the deterministic findings are still
produced.  There is **no hard dependency** on a model backend.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

try:
    from tools.eval import Finding
except ImportError:
    from eval import Finding

try:
    from tools.llm_provider import get_provider
except ImportError:
    try:
        from llm_provider import get_provider
    except ImportError:
        get_provider = None  # type: ignore[assignment]

_SIGNAL_ID = "G6-disambiguation"
_FINDING_CLASS = "deterministic"

# Minimum fraction of shared tags to flag structural overlap (0 < threshold ≤ 1).
_TAG_OVERLAP_THRESHOLD = 0.5
# Minimum number of tags an artifact must have for tag-overlap to be meaningful.
_MIN_TAGS = 2
# Minimum co-citation count before two artifacts are flagged as co-cited.
_CO_CITE_MIN = 2


def _normalise(text: str) -> str:
    """Case-fold and strip whitespace for name comparison."""
    return re.sub(r"\s+", " ", text.strip().casefold())


def _collect_names(artifact) -> Set[str]:
    """Return the full set of normalised names/aliases for *artifact*."""
    names: Set[str] = set()
    title = artifact.frontmatter.get("title", "")
    if title:
        names.add(_normalise(str(title)))
    for alias in artifact.frontmatter.get("aliases") or []:
        n = _normalise(str(alias))
        if n:
            names.add(n)
    return names


def _rel_path(artifact, model) -> str:
    try:
        return str(artifact.path.relative_to(model.root))
    except ValueError:
        return str(artifact.path)


# ---------------------------------------------------------------------------
# Deterministic candidate detection
# ---------------------------------------------------------------------------

def _shared_name_candidates(model) -> List[Tuple[str, str, str]]:
    """Return ``(path_a, path_b, shared_name)`` tuples for name/alias collisions."""
    name_to_paths: Dict[str, List[str]] = defaultdict(list)
    for artifact in model.artifacts:
        rel = _rel_path(artifact, model)
        for name in _collect_names(artifact):
            name_to_paths[name].append(rel)

    results: List[Tuple[str, str, str]] = []
    for name, paths in name_to_paths.items():
        if len(paths) < 2:
            continue
        seen: Set[Tuple[str, str]] = set()
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                pair = (paths[i], paths[j])
                if pair not in seen:
                    seen.add(pair)
                    results.append((paths[i], paths[j], name))
    return results


def _co_cited_candidates(model) -> List[Tuple[str, str, int]]:
    """Return ``(path_a, path_b, co_cite_count)`` for frequently co-cited pairs."""
    # co_cite_count[frozenset{a, b}] = number of artefacts that link both.
    co_cite: Dict[frozenset, int] = defaultdict(int)
    for artifact in model.artifacts:
        linked = artifact.frontmatter.get("linked_concepts") or []
        linked_norm = [_normalise(str(lc)) for lc in linked if lc]
        if len(linked_norm) < 2:
            continue
        # Map normalised concept names back to file paths.
        norm_to_path: Dict[str, str] = {}
        for art2 in model.artifacts:
            rel2 = _rel_path(art2, model)
            for name in _collect_names(art2):
                norm_to_path[name] = rel2
        resolved = [norm_to_path[n] for n in linked_norm if n in norm_to_path]
        for i in range(len(resolved)):
            for j in range(i + 1, len(resolved)):
                key = frozenset({resolved[i], resolved[j]})
                co_cite[key] += 1

    results: List[Tuple[str, str, int]] = []
    for pair_set, count in co_cite.items():
        if count < _CO_CITE_MIN:
            continue
        pair = sorted(pair_set)
        results.append((pair[0], pair[1], count))
    return results


def _tag_overlap_candidates(model) -> List[Tuple[str, str, float]]:
    """Return ``(path_a, path_b, overlap_fraction)`` for knowledge-notes with high tag overlap."""
    knowledge_notes = [
        a
        for a in model.artifacts
        if a.frontmatter.get("artifact_type") == "knowledge-note"
        and len(a.frontmatter.get("tags") or []) >= _MIN_TAGS
    ]
    results: List[Tuple[str, str, float]] = []
    for i in range(len(knowledge_notes)):
        for j in range(i + 1, len(knowledge_notes)):
            a, b = knowledge_notes[i], knowledge_notes[j]
            tags_a = {_normalise(str(t)) for t in (a.frontmatter.get("tags") or [])}
            tags_b = {_normalise(str(t)) for t in (b.frontmatter.get("tags") or [])}
            if not tags_a or not tags_b:
                continue
            intersection = tags_a & tags_b
            union = tags_a | tags_b
            jaccard = len(intersection) / len(union)
            if jaccard >= _TAG_OVERLAP_THRESHOLD:
                pa = _rel_path(a, model)
                pb = _rel_path(b, model)
                results.append((pa, pb, jaccard))
    return results


# ---------------------------------------------------------------------------
# Optional LLM suggestion
# ---------------------------------------------------------------------------

_SUGGESTION_SYSTEM = (
    "You are a wiki curation assistant. Classify whether two overlapping wiki "
    "concepts should be merged into one note or split into two distinct notes. "
    "Reply with exactly one word: 'merge' or 'split', then a brief reason."
)


def _llm_suggestion(path_a: str, path_b: str, reason: str, provider) -> str | None:
    """Ask the provider for a merge/split suggestion. Returns None on failure."""
    if provider is None or not provider.enabled:
        return None
    prompt = (
        f"Wiki notes that overlap:\n"
        f"  A: {path_a}\n"
        f"  B: {path_b}\n"
        f"Overlap detected via: {reason}\n"
        f"Should these be merged or split?"
    )
    try:
        return provider.complete(prompt, system=_SUGGESTION_SYSTEM)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Signal implementation
# ---------------------------------------------------------------------------

class _DisambiguationSignal:
    id: str = _SIGNAL_ID
    finding_class: str = _FINDING_CLASS

    def run(self, model) -> List[Finding]:
        findings: List[Finding] = []

        # Obtain provider once; may be disabled — that is fine.
        provider = None
        if get_provider is not None:
            try:
                provider = get_provider()
            except Exception:
                provider = None

        # 1. Shared name / alias collisions
        for path_a, path_b, shared_name in _shared_name_candidates(model):
            findings.append(
                Finding(
                    signal_id=_SIGNAL_ID,
                    finding_class=_FINDING_CLASS,
                    severity="warn",
                    implicated=[path_a, path_b],
                    explanation=(
                        f"candidate: shared name/alias '{shared_name}' — "
                        "potential merge candidate"
                    ),
                )
            )
            suggestion = _llm_suggestion(path_a, path_b, f"shared name '{shared_name}'", provider)
            if suggestion:
                findings.append(
                    Finding(
                        signal_id=_SIGNAL_ID,
                        finding_class="llm",
                        severity="info",
                        implicated=[path_a, path_b],
                        explanation=f"suggestion: {suggestion}",
                    )
                )

        # 2. Structural co-citation overlap
        for path_a, path_b, count in _co_cited_candidates(model):
            findings.append(
                Finding(
                    signal_id=_SIGNAL_ID,
                    finding_class=_FINDING_CLASS,
                    severity="info",
                    implicated=[path_a, path_b],
                    explanation=(
                        f"candidate: co-cited {count}× in linked_concepts — "
                        "structural overlap detected"
                    ),
                )
            )
            suggestion = _llm_suggestion(
                path_a, path_b, f"co-cited {count} times", provider
            )
            if suggestion:
                findings.append(
                    Finding(
                        signal_id=_SIGNAL_ID,
                        finding_class="llm",
                        severity="info",
                        implicated=[path_a, path_b],
                        explanation=f"suggestion: {suggestion}",
                    )
                )

        # 3. Tag overlap (knowledge-notes only)
        for path_a, path_b, jaccard in _tag_overlap_candidates(model):
            findings.append(
                Finding(
                    signal_id=_SIGNAL_ID,
                    finding_class=_FINDING_CLASS,
                    severity="info",
                    implicated=[path_a, path_b],
                    explanation=(
                        f"candidate: tag overlap {jaccard:.0%} (Jaccard) — "
                        "possible split or merge candidate"
                    ),
                )
            )
            suggestion = _llm_suggestion(
                path_a, path_b, f"tag Jaccard {jaccard:.2f}", provider
            )
            if suggestion:
                findings.append(
                    Finding(
                        signal_id=_SIGNAL_ID,
                        finding_class="llm",
                        severity="info",
                        implicated=[path_a, path_b],
                        explanation=f"suggestion: {suggestion}",
                    )
                )

        return findings


SIGNAL = _DisambiguationSignal()
