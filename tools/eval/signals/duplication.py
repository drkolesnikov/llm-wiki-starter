#!/usr/bin/env python3
"""G2-duplication signal — deterministic near-duplicate artifact detection.

Compares every pair of wiki artifacts by token-shingle Jaccard similarity over
normalised body text. Pairs whose similarity exceeds *threshold* (default 0.8)
are emitted as advisory :class:`tools.eval.Finding` objects, ranked from most-
to least-similar. No LLM, no network access.

Configuration
-------------
The default threshold (0.8) can be changed at runtime by mutating
``SIGNAL.threshold`` before the suite is called, or by constructing a custom
:class:`_DuplicationSignal` with a different value.

Shingle parameters
------------------
``SHINGLE_SIZE`` controls the n-gram width (default 3 tokens). Tokens are
whitespace-split words lowercased with all non-alphanumeric characters stripped,
so punctuation and casing differences do not inflate dissimilarity.
"""

from __future__ import annotations

import re
from itertools import combinations
from typing import List

try:
    from tools.eval import Finding
except ImportError:  # script invocation: tools/ on sys.path
    from eval import Finding  # type: ignore[no-reuse-named-type]


#: Width of the token shingles used for Jaccard similarity.
SHINGLE_SIZE: int = 3


def _tokenize(text: str) -> list[str]:
    """Lower-case, strip non-alphanumeric chars, split on whitespace."""
    return [re.sub(r"[^a-z0-9]", "", t) for t in text.lower().split() if re.sub(r"[^a-z0-9]", "", t)]


def _shingles(tokens: list[str], k: int = SHINGLE_SIZE) -> frozenset[tuple[str, ...]]:
    """Return the set of k-token shingles from *tokens*."""
    if len(tokens) < k:
        # Fall back to the full token multiset represented as a single shingle
        # so short documents still produce a non-empty shingle set.
        return frozenset([tuple(tokens)])
    return frozenset(tuple(tokens[i : i + k]) for i in range(len(tokens) - k + 1))


def _jaccard(a: frozenset, b: frozenset) -> float:
    """Jaccard similarity between two sets. Returns 0.0 when both are empty."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


class _DuplicationSignal:
    """Deterministic near-duplicate detection over wiki artifact body text."""

    id: str = "G2-duplication"
    finding_class: str = "deterministic"

    def __init__(self, threshold: float = 0.8) -> None:
        self.threshold = threshold

    def run(self, model) -> List[Finding]:
        """Return ranked :class:`Finding` objects for near-duplicate pairs.

        Parameters
        ----------
        model:
            A :class:`tools.wiki_model.RepoModel` produced by
            :func:`tools.wiki_model.load_repo_model`.

        Returns
        -------
        list[Finding]
            One finding per pair whose Jaccard similarity >= ``self.threshold``,
            ordered from highest to lowest similarity (most-duplicated first).
        """
        artifacts = list(model.artifacts)
        if len(artifacts) < 2:
            return []

        # Pre-compute shingle sets for all artifacts.
        shingle_map: dict[int, frozenset] = {}
        for i, artifact in enumerate(artifacts):
            tokens = _tokenize(artifact.body)
            shingle_map[i] = _shingles(tokens)

        # Compare every pair and collect those above the threshold.
        scored: list[tuple[float, str, str]] = []
        for i, j in combinations(range(len(artifacts)), 2):
            score = _jaccard(shingle_map[i], shingle_map[j])
            if score >= self.threshold:
                path_i = str(artifacts[i].path)
                path_j = str(artifacts[j].path)
                scored.append((score, path_i, path_j))

        # Sort descending by similarity.
        scored.sort(key=lambda t: t[0], reverse=True)

        findings: List[Finding] = []
        for score, path_i, path_j in scored:
            findings.append(
                Finding(
                    signal_id=self.id,
                    finding_class=self.finding_class,
                    severity="warn",
                    implicated=[path_i, path_j],
                    explanation=(
                        f"Near-duplicate pair (Jaccard={score:.3f} >= {self.threshold}): "
                        f"{path_i!r} and {path_j!r}"
                    ),
                )
            )
        return findings


#: Module-level instance auto-discovered by the eval suite.
SIGNAL = _DuplicationSignal()
