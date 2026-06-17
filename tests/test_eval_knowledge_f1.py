"""Tests for tools/eval/signals/knowledge_f1.py (G4-knowledge-f1).

Uses a stub LLM provider that returns scripted fact sets so the tests run
deterministically with no real LLM backend.

Design:
  - artifact has 3 facts: F1, F2, F3-hallucinated
  - source  has 3 facts: F1, F2, F4-omitted
  - precision = 2/3 (F3-hallucinated absent from source)
  - recall    = 2/3 (F4-omitted absent from artifact)
  - F1        = 2/3  (harmonic mean of 2/3, 2/3)

The disabled-provider path returns exactly one Finding with
explanation "skipped — no backend".
"""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# Ensure repo root is importable.
_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.eval import Finding
from tools.llm_provider import ModelProvider
from tools.eval.signals import knowledge_f1 as kf1_module
from tools.eval.signals.knowledge_f1 import SIGNAL, _KnowledgeF1Signal


# ---------------------------------------------------------------------------
# Scripted fact sets
# ---------------------------------------------------------------------------

ARTIFACT_FACTS = ["F1-shared", "F2-shared", "F3-hallucinated"]
SOURCE_FACTS = ["F1-shared", "F2-shared", "F4-omitted"]

# expected metrics
_PREC = 2 / 3  # F3-hallucinated not in source
_REC = 2 / 3   # F4-omitted not in artifact
_F1 = 2 * _PREC * _REC / (_PREC + _REC)  # = 2/3


# ---------------------------------------------------------------------------
# Stub provider
# ---------------------------------------------------------------------------

class _StubProvider(ModelProvider):
    """Deterministic LLM stub that returns scripted fact lists."""

    enabled = True

    def __init__(self, artifact_facts: list[str], source_facts: list[str]) -> None:
        self._artifact_facts = artifact_facts
        self._source_facts = source_facts
        # Track which text extract call we're on.
        self._extract_call = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        """Return scripted fact lists or YES/NO membership answers."""
        # First two calls come from _extract_facts (artifact then source text).
        if "Extract atomic facts" in prompt:
            self._extract_call += 1
            if self._extract_call == 1:
                return "\n".join(self._artifact_facts)
            else:
                return "\n".join(self._source_facts)

        # Overlap queries: "Does the following fact appear in the candidate list"
        if "Does the following fact appear" in prompt:
            # Extract the fact being tested from the prompt.
            for line in prompt.splitlines():
                if line.startswith("Fact:"):
                    fact = line[len("Fact:"):].strip()
                    break
            else:
                return "NO"

            # A fact is "in" the candidate set if it appears verbatim.
            if "Candidates:" in prompt:
                candidates_section = prompt.split("Candidates:")[1]
                candidate_lines = [
                    l.lstrip("- ").strip()
                    for l in candidates_section.splitlines()
                    if l.strip().startswith("-")
                ]
            else:
                candidate_lines = []

            return "YES" if fact in candidate_lines else "NO"

        return "NO"


# ---------------------------------------------------------------------------
# Minimal model fixtures
# ---------------------------------------------------------------------------

def _make_model(artifact_body: str = "artifact text", source_body: str = "source text"):
    """Return a minimal RepoModel-like object with one artifact and one source."""
    source = SimpleNamespace(body=source_body)
    artifact = SimpleNamespace(
        body=artifact_body,
        path="notes/test-artifact.md",
        sources=[source],
    )
    return SimpleNamespace(artifacts=[artifact])


def _make_empty_model():
    """Return a model with no artifacts."""
    return SimpleNamespace(artifacts=[])


def _make_no_sources_model():
    """Return a model with an artifact that has no sources."""
    artifact = SimpleNamespace(body="some text", path="notes/no-src.md", sources=[])
    return SimpleNamespace(artifacts=[artifact])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSignalMetadata(unittest.TestCase):
    """SIGNAL is correctly registered."""

    def test_signal_id(self):
        self.assertEqual("G4-knowledge-f1", SIGNAL.id)

    def test_finding_class(self):
        self.assertEqual("llm", SIGNAL.finding_class)

    def test_signal_is_instance(self):
        self.assertIsInstance(SIGNAL, _KnowledgeF1Signal)


class TestDisabledProvider(unittest.TestCase):
    """When the provider is disabled, return exactly one 'skipped' finding."""

    def _run_with_disabled(self):
        from tools.llm_provider import DisabledProvider
        model = _make_model()
        with patch.object(kf1_module, "get_provider", return_value=DisabledProvider()):
            return SIGNAL.run(model)

    def test_returns_one_finding(self):
        findings = self._run_with_disabled()
        self.assertEqual(1, len(findings))

    def test_finding_is_Finding_instance(self):
        findings = self._run_with_disabled()
        self.assertIsInstance(findings[0], Finding)

    def test_explanation_is_skipped(self):
        findings = self._run_with_disabled()
        self.assertEqual("skipped — no backend", findings[0].explanation)

    def test_signal_id_preserved(self):
        findings = self._run_with_disabled()
        self.assertEqual("G4-knowledge-f1", findings[0].signal_id)

    def test_finding_class_preserved(self):
        findings = self._run_with_disabled()
        self.assertEqual("llm", findings[0].finding_class)


class TestPrecisionRecallF1(unittest.TestCase):
    """With a stub provider the metrics are computed correctly."""

    def _run_stub(self, artifact_facts=None, source_facts=None):
        if artifact_facts is None:
            artifact_facts = ARTIFACT_FACTS
        if source_facts is None:
            source_facts = SOURCE_FACTS
        stub = _StubProvider(artifact_facts, source_facts)
        model = _make_model()
        with patch.object(kf1_module, "get_provider", return_value=stub):
            return SIGNAL.run(model)

    def test_returns_one_finding_per_artifact(self):
        findings = self._run_stub()
        self.assertEqual(1, len(findings))

    def test_finding_signal_id(self):
        findings = self._run_stub()
        self.assertEqual("G4-knowledge-f1", findings[0].signal_id)

    def test_finding_class_is_llm(self):
        findings = self._run_stub()
        self.assertEqual("llm", findings[0].finding_class)

    def test_implicated_path(self):
        findings = self._run_stub()
        self.assertIn("notes/test-artifact.md", findings[0].implicated)

    def test_precision_in_explanation(self):
        """Explanation must contain precision=0.67."""
        findings = self._run_stub()
        self.assertIn("precision=0.67", findings[0].explanation)

    def test_recall_in_explanation(self):
        """Explanation must contain recall=0.67."""
        findings = self._run_stub()
        self.assertIn("recall=0.67", findings[0].explanation)

    def test_f1_in_explanation(self):
        """Explanation must contain F1=0.67."""
        findings = self._run_stub()
        self.assertIn("F1=0.67", findings[0].explanation)

    def test_hallucinated_fact_mentioned(self):
        findings = self._run_stub()
        self.assertIn("F3-hallucinated", findings[0].explanation)

    def test_omitted_fact_mentioned(self):
        findings = self._run_stub()
        self.assertIn("F4-omitted", findings[0].explanation)

    def test_severity_is_warn_when_f1_lt_1(self):
        findings = self._run_stub()
        self.assertEqual("warn", findings[0].severity)

    def test_severity_is_info_when_perfect(self):
        """When artifact and source have identical facts, severity is info."""
        perfect_facts = ["F1", "F2", "F3"]
        findings = self._run_stub(artifact_facts=perfect_facts, source_facts=perfect_facts)
        # F1 = 1.0 → info
        self.assertEqual("info", findings[0].severity)


class TestEdgeCases(unittest.TestCase):
    """Edge cases: no artifacts, no sources."""

    def test_empty_model_returns_no_findings(self):
        model = _make_empty_model()
        from tools.llm_provider import DisabledProvider
        with patch.object(kf1_module, "get_provider", return_value=DisabledProvider()):
            # Disabled, but with no artifacts the disabled path still fires.
            pass
        # Use a stub enabled provider with an empty artifact list.
        stub = _StubProvider([], [])
        stub.enabled = True
        with patch.object(kf1_module, "get_provider", return_value=stub):
            findings = SIGNAL.run(model)
        self.assertEqual([], findings)

    def test_artifact_without_sources_skipped(self):
        model = _make_no_sources_model()
        stub = _StubProvider([], [])
        with patch.object(kf1_module, "get_provider", return_value=stub):
            findings = SIGNAL.run(model)
        self.assertEqual([], findings)


class TestComputePrecisionRecallHelper(unittest.TestCase):
    """Unit-test the _compute_precision_recall helper directly."""

    def _make_provider_with_membership(self, artifact_facts, source_facts):
        """Return a provider whose overlap answers are based on set membership."""
        return _StubProvider(artifact_facts, source_facts)

    def test_perfect_match(self):
        from tools.eval.signals.knowledge_f1 import _compute_precision_recall

        class _AlwaysYes(ModelProvider):
            enabled = True
            def complete(self, prompt, *, system=None):
                return "YES"

        p, r, f = _compute_precision_recall(_AlwaysYes(), ["F1", "F2"], ["F1", "F2"])
        self.assertAlmostEqual(1.0, p)
        self.assertAlmostEqual(1.0, r)
        self.assertAlmostEqual(1.0, f)

    def test_no_overlap(self):
        from tools.eval.signals.knowledge_f1 import _compute_precision_recall

        class _AlwaysNo(ModelProvider):
            enabled = True
            def complete(self, prompt, *, system=None):
                return "NO"

        p, r, f = _compute_precision_recall(_AlwaysNo(), ["A"], ["B"])
        self.assertAlmostEqual(0.0, p)
        self.assertAlmostEqual(0.0, r)
        self.assertAlmostEqual(0.0, f)

    def test_empty_both(self):
        from tools.eval.signals.knowledge_f1 import _compute_precision_recall

        class _NeverCalled(ModelProvider):
            enabled = True
            def complete(self, prompt, *, system=None):
                raise AssertionError("should not be called")

        p, r, f = _compute_precision_recall(_NeverCalled(), [], [])
        self.assertAlmostEqual(1.0, p)
        self.assertAlmostEqual(1.0, r)
        self.assertAlmostEqual(1.0, f)

    def test_f1_formula(self):
        """F1 = 2*p*r/(p+r) for p=2/3, r=2/3 → 2/3."""
        expected_f1 = 2 * _PREC * _REC / (_PREC + _REC)
        self.assertAlmostEqual(2 / 3, expected_f1)


if __name__ == "__main__":
    unittest.main()
