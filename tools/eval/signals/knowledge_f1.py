"""G4-knowledge-f1: content precision/recall (LLM-backed).

This signal extracts the atomic fact set of a wiki artifact and the fact set
of its cited source(s) via the configured LLM provider, then computes:

- **precision** — fraction of artifact facts that appear in the source
  (facts absent from the source are hallucinations).
- **recall** — fraction of source facts that appear in the artifact
  (facts absent from the artifact are omissions).
- **F1** — harmonic mean of precision and recall.

One :class:`tools.eval.Finding` is emitted per artifact that has at least one
citation.  When the provider is disabled, a single "skipped — no backend"
finding is returned instead.

Discovery: expose this module's ``SIGNAL`` object and drop this file into
``tools/eval/signals/``.  No edit to :mod:`tools.eval` is required.
"""

from __future__ import annotations

import sys
import os
import re
from typing import List

# Ensure the repo root is on sys.path when invoked directly.
_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.eval import Finding
from tools.llm_provider import get_provider


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_FACTS_SYSTEM = (
    "You are a fact-extraction assistant. "
    "Extract every distinct atomic fact from the provided text. "
    "Return one fact per line. "
    "Do not number the lines. "
    "Be concise; do not repeat semantically equivalent facts."
)

_FACTS_PROMPT = "Extract atomic facts from the following text:\n\n{text}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_facts(provider, text: str) -> list[str]:
    """Call the LLM to extract atomic facts from *text*.

    Returns a deduplicated list of non-empty fact strings.
    """
    raw = provider.complete(
        _FACTS_PROMPT.format(text=text.strip()),
        system=_FACTS_SYSTEM,
    )
    seen: set[str] = set()
    facts: list[str] = []
    for line in raw.splitlines():
        fact = line.strip()
        if fact and fact not in seen:
            seen.add(fact)
            facts.append(fact)
    return facts


def _overlap_prompt(fact: str, candidates: list[str]) -> str:
    candidates_text = "\n".join(f"- {c}" for c in candidates)
    return (
        f"Does the following fact appear in the candidate list "
        f"(semantically, not necessarily verbatim)?\n\n"
        f"Fact: {fact}\n\n"
        f"Candidates:\n{candidates_text}\n\n"
        f"Answer only YES or NO."
    )


def _fact_in_set(provider, fact: str, candidate_set: list[str]) -> bool:
    """Return True when *fact* is semantically present in *candidate_set*."""
    if not candidate_set:
        return False
    answer = provider.complete(_overlap_prompt(fact, candidate_set))
    return answer.strip().upper().startswith("Y")


def _compute_precision_recall(
    provider,
    artifact_facts: list[str],
    source_facts: list[str],
) -> tuple[float, float, float]:
    """Return (precision, recall, f1) in [0, 1].

    - precision: |artifact_facts ∩ source_facts| / |artifact_facts|
    - recall:    |source_facts ∩ artifact_facts| / |source_facts|
    """
    if not artifact_facts and not source_facts:
        return 1.0, 1.0, 1.0

    if artifact_facts:
        tp_precision = sum(
            1 for f in artifact_facts if _fact_in_set(provider, f, source_facts)
        )
        precision = tp_precision / len(artifact_facts)
    else:
        precision = 1.0  # no artifact facts → nothing to hallucinate

    if source_facts:
        tp_recall = sum(
            1 for f in source_facts if _fact_in_set(provider, f, artifact_facts)
        )
        recall = tp_recall / len(source_facts)
    else:
        recall = 1.0  # no source facts → nothing to omit

    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)

    return precision, recall, f1


# ---------------------------------------------------------------------------
# Signal implementation
# ---------------------------------------------------------------------------

_SIGNAL_ID = "G4-knowledge-f1"
_FINDING_CLASS = "llm"


class _KnowledgeF1Signal:
    """Content precision/recall signal (LLM-backed)."""

    id: str = _SIGNAL_ID
    finding_class: str = _FINDING_CLASS

    def run(self, model) -> List[Finding]:  # noqa: ANN001
        """Evaluate every artifact with citations and return findings.

        Parameters
        ----------
        model:
            A :class:`tools.wiki_model.RepoModel`.  Each artifact's
            ``body`` text and its first cited source's ``body`` text are
            passed to the LLM.

        Returns
        -------
        list[Finding]
            One finding per evaluated artifact, or a single "skipped"
            finding when the provider is disabled.
        """
        provider = get_provider()
        if not provider.enabled:
            return [
                Finding(
                    signal_id=self.id,
                    finding_class=self.finding_class,
                    severity="info",
                    implicated=[],
                    explanation="skipped — no backend",
                )
            ]

        findings: List[Finding] = []

        # Walk every artifact that has at least one cited source.
        for artifact in getattr(model, "artifacts", []):
            sources = getattr(artifact, "sources", []) or []
            if not sources:
                continue

            artifact_text = getattr(artifact, "body", "") or ""
            source_text = "\n\n".join(
                getattr(src, "body", "") or "" for src in sources
            )

            if not artifact_text.strip() and not source_text.strip():
                continue

            artifact_facts = _extract_facts(provider, artifact_text)
            source_facts = _extract_facts(provider, source_text)

            precision, recall, f1 = _compute_precision_recall(
                provider, artifact_facts, source_facts
            )

            hallucinated = [
                f for f in artifact_facts
                if not _fact_in_set(provider, f, source_facts)
            ]
            omitted = [
                f for f in source_facts
                if not _fact_in_set(provider, f, artifact_facts)
            ]

            path = getattr(artifact, "path", str(artifact))
            explanation = (
                f"precision={precision:.2f}, recall={recall:.2f}, F1={f1:.2f}. "
                f"Hallucinated facts ({len(hallucinated)}): "
                f"{hallucinated[:3]}{'…' if len(hallucinated) > 3 else ''}. "
                f"Omitted facts ({len(omitted)}): "
                f"{omitted[:3]}{'…' if len(omitted) > 3 else ''}."
            )

            if f1 < 1.0:
                severity = "warn"
            else:
                severity = "info"

            findings.append(
                Finding(
                    signal_id=self.id,
                    finding_class=self.finding_class,
                    severity=severity,
                    implicated=[path],
                    explanation=explanation,
                )
            )

        return findings


SIGNAL = _KnowledgeF1Signal()
