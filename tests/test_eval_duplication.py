"""Tests for the G2-duplication eval signal.

Exercises the deterministic near-duplicate detection over wiki artifact body
text using token-shingle Jaccard similarity. All tests use unittest (not
pytest) as required by the project conventions.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from tools.eval.signals.duplication import (
    SIGNAL,
    _DuplicationSignal,
    _jaccard,
    _shingles,
    _tokenize,
)
from tools.eval import Finding
from tools.wiki_model import Artifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_model(*bodies: str) -> MagicMock:
    """Build a fake RepoModel whose artifacts have the given body texts."""
    artifacts = [
        Artifact(path=Path(f"note_{i}.md"), frontmatter={}, body=body)
        for i, body in enumerate(bodies)
    ]
    model = MagicMock()
    model.artifacts = artifacts
    return model


# ---------------------------------------------------------------------------
# Unit tests: internal helpers
# ---------------------------------------------------------------------------

class TokenizeTests(unittest.TestCase):
    def test_lowercases_and_strips_punctuation(self):
        tokens = _tokenize("Hello, World! This is a test.")
        self.assertEqual(["hello", "world", "this", "is", "a", "test"], tokens)

    def test_empty_string(self):
        self.assertEqual([], _tokenize(""))

    def test_only_punctuation(self):
        self.assertEqual([], _tokenize("!!! --- ..."))

    def test_digits_preserved(self):
        tokens = _tokenize("GPT-4 vs GPT-3.5")
        self.assertIn("gpt4", tokens)


class ShingleTests(unittest.TestCase):
    def test_basic_trigram_shingles(self):
        tokens = ["a", "b", "c", "d"]
        result = _shingles(tokens, k=3)
        self.assertIn(("a", "b", "c"), result)
        self.assertIn(("b", "c", "d"), result)
        self.assertEqual(2, len(result))

    def test_short_text_falls_back_to_full_tuple(self):
        tokens = ["a", "b"]
        result = _shingles(tokens, k=3)
        self.assertEqual(frozenset({("a", "b")}), result)

    def test_empty_tokens(self):
        result = _shingles([], k=3)
        self.assertEqual(frozenset({()}), result)


class JaccardTests(unittest.TestCase):
    def test_identical_sets_return_one(self):
        s = frozenset({("a", "b"), ("b", "c")})
        self.assertAlmostEqual(1.0, _jaccard(s, s))

    def test_disjoint_sets_return_zero(self):
        a = frozenset({("a", "b")})
        b = frozenset({("c", "d")})
        self.assertAlmostEqual(0.0, _jaccard(a, b))

    def test_partial_overlap(self):
        a = frozenset({("a", "b"), ("b", "c")})
        b = frozenset({("b", "c"), ("c", "d")})
        # intersection = 1, union = 3 → 1/3
        self.assertAlmostEqual(1 / 3, _jaccard(a, b))

    def test_both_empty(self):
        self.assertAlmostEqual(0.0, _jaccard(frozenset(), frozenset()))


# ---------------------------------------------------------------------------
# Integration tests: _DuplicationSignal.run()
# ---------------------------------------------------------------------------

class DuplicationSignalTests(unittest.TestCase):
    """Core behavioural tests for the signal."""

    # A body long enough for 3-shingles to be meaningful (20+ tokens).
    _BASE = (
        "The quick brown fox jumps over the lazy dog near the river bank "
        "while the sun sets slowly in the west end of town today"
    )

    def _make_signal(self, threshold: float = 0.8) -> _DuplicationSignal:
        return _DuplicationSignal(threshold=threshold)

    # --- Near-duplicate pair is ranked above threshold ---

    def test_identical_bodies_produce_a_finding(self):
        signal = self._make_signal(threshold=0.8)
        model = _make_model(self._BASE, self._BASE)
        findings = signal.run(model)
        self.assertEqual(1, len(findings))
        self.assertIsInstance(findings[0], Finding)
        self.assertEqual("G2-duplication", findings[0].signal_id)
        self.assertEqual("deterministic", findings[0].finding_class)
        self.assertEqual("warn", findings[0].severity)
        self.assertEqual(2, len(findings[0].implicated))

    def test_near_duplicate_pair_ranked_above_threshold(self):
        """A pair with one word changed should still be very similar."""
        near_dup = self._BASE.replace("quick", "fast")
        signal = self._make_signal(threshold=0.5)
        model = _make_model(self._BASE, near_dup)
        findings = signal.run(model)
        self.assertGreater(len(findings), 0, "near-duplicate pair should exceed threshold")
        # Extract similarity from explanation
        explanation = findings[0].explanation
        self.assertIn("Jaccard=", explanation)

    def test_findings_ranked_most_similar_first(self):
        """When multiple pairs qualify, they are ranked high-to-low."""
        # Three docs: [0,1] are identical; [0,2] are moderately similar.
        doc_a = self._BASE
        doc_b = self._BASE  # identical to a
        doc_c = self._BASE[:80] + " completely different words here now yes indeed"
        signal = self._make_signal(threshold=0.1)
        model = _make_model(doc_a, doc_b, doc_c)
        findings = signal.run(model)
        self.assertGreaterEqual(len(findings), 2)
        # First finding should have higher (or equal) Jaccard than second.
        def _score(f: Finding) -> float:
            import re
            m = re.search(r"Jaccard=([\d.]+)", f.explanation)
            return float(m.group(1)) if m else 0.0
        scores = [_score(f) for f in findings]
        for i in range(len(scores) - 1):
            self.assertGreaterEqual(scores[i], scores[i + 1])

    # --- Dissimilar artifacts → no findings ---

    def test_dissimilar_artifacts_produce_no_findings(self):
        body_a = (
            "Transformer architectures use attention mechanisms to process "
            "sequential data in parallel enabling faster training times "
            "and better performance on many natural language tasks"
        )
        body_b = (
            "The French Revolution began in seventeen eighty nine overthrowing "
            "the monarchy and establishing a republic through violent social "
            "and political upheaval across the entire country of France"
        )
        signal = self._make_signal(threshold=0.8)
        model = _make_model(body_a, body_b)
        findings = signal.run(model)
        self.assertEqual([], findings)

    def test_empty_model_produces_no_findings(self):
        signal = self._make_signal()
        model = _make_model()
        self.assertEqual([], signal.run(model))

    def test_single_artifact_produces_no_findings(self):
        signal = self._make_signal()
        model = _make_model(self._BASE)
        self.assertEqual([], signal.run(model))

    # --- Threshold is configurable ---

    def test_threshold_configurable_lower_finds_more_pairs(self):
        body_a = self._BASE
        body_b = self._BASE.replace("quick", "speedy").replace("lazy", "slow")
        # At strict threshold=0.9 the pair may not qualify; at 0.5 it likely does.
        strict = self._make_signal(threshold=0.95)
        lenient = self._make_signal(threshold=0.5)
        model = _make_model(body_a, body_b)
        strict_findings = strict.run(model)
        lenient_findings = lenient.run(model)
        self.assertGreaterEqual(len(lenient_findings), len(strict_findings))

    def test_threshold_at_one_only_matches_identical(self):
        body_a = self._BASE
        body_b = self._BASE + " extra word"
        signal = self._make_signal(threshold=1.0)
        model = _make_model(body_a, body_b)
        # The extra word changes the shingle set, so Jaccard < 1.0.
        self.assertEqual([], signal.run(model))

    def test_threshold_at_zero_matches_all_pairs(self):
        body_a = self._BASE
        body_b = "completely unrelated short text about something else entirely"
        signal = self._make_signal(threshold=0.0)
        model = _make_model(body_a, body_b)
        findings = signal.run(model)
        self.assertEqual(1, len(findings))

    # --- Module-level SIGNAL object ---

    def test_module_signal_has_correct_id_and_class(self):
        self.assertEqual("G2-duplication", SIGNAL.id)
        self.assertEqual("deterministic", SIGNAL.finding_class)

    def test_module_signal_default_threshold(self):
        self.assertAlmostEqual(0.8, SIGNAL.threshold)

    def test_module_signal_is_callable(self):
        model = _make_model()
        result = SIGNAL.run(model)
        self.assertIsInstance(result, list)

    def test_module_signal_satisfies_protocol(self):
        from tools.eval import Signal
        self.assertIsInstance(SIGNAL, Signal)


if __name__ == "__main__":
    unittest.main()
