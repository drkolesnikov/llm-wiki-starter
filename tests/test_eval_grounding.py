"""Tests for the G1-grounding eval signal.

Uses a stub ModelProvider (not pytest, unittest only) injected via
unittest.mock.patch on the signal module's ``get_provider`` reference so the
real get_provider() is never called.
"""

import unittest
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

from tools.eval import Finding
from tools.eval.signals import grounding as grounding_mod
from tools.llm_provider import ModelProvider
from tools.wiki_model import Artifact, RepoModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_model(body: str, sources: dict | None = None) -> RepoModel:
    """Build a minimal RepoModel with one artifact for testing."""
    artifact = Artifact(
        path=Path("notes/test.md"),
        frontmatter={},
        body=body,
    )
    return RepoModel(
        root=Path("/fake/root"),
        artifacts=[artifact],
        sources=sources or {},
    )


class _StubProvider(ModelProvider):
    """Scripted provider whose ``complete()`` returns preset responses."""

    enabled: bool = True

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._index = 0

    def complete(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        if self._index >= len(self._responses):
            return "grounded"
        response = self._responses[self._index]
        self._index += 1
        return response


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class GroundingSignalMetaTests(unittest.TestCase):
    """Signal object conforms to the Signal protocol."""

    def test_signal_id(self):
        self.assertEqual("G1-grounding", grounding_mod.SIGNAL.id)

    def test_finding_class(self):
        self.assertEqual("llm", grounding_mod.SIGNAL.finding_class)


class GroundingSignalDisabledTests(unittest.TestCase):
    """When the provider is disabled, a single 'skipped' finding is returned."""

    def test_disabled_provider_returns_skipped_finding(self):
        # Use the real get_provider() which returns DisabledProvider by default.
        model = _make_model("The sky is blue.")
        findings = grounding_mod.SIGNAL.run(model)
        self.assertEqual(1, len(findings))
        self.assertIn("skipped", findings[0].explanation)
        self.assertIn("no backend", findings[0].explanation)

    def test_disabled_provider_finding_class_is_llm(self):
        model = _make_model("Some text.")
        findings = grounding_mod.SIGNAL.run(model)
        self.assertEqual("llm", findings[0].finding_class)

    def test_disabled_provider_severity_is_info(self):
        model = _make_model("Some text.")
        findings = grounding_mod.SIGNAL.run(model)
        self.assertEqual("info", findings[0].severity)


class GroundingSignalStubProviderTests(unittest.TestCase):
    """With a stub provider that reports 'ungrounded', the claim is flagged."""

    def _run_with_stub(self, model: RepoModel, responses: list[str]) -> list[Finding]:
        stub = _StubProvider(responses)
        with patch.object(grounding_mod, "get_provider", return_value=stub):
            return grounding_mod.SIGNAL.run(model)

    def test_ungrounded_claim_produces_finding(self):
        model = _make_model("The moon is made of cheese.")
        findings = self._run_with_stub(model, ["ungrounded"])
        self.assertEqual(1, len(findings))
        self.assertIn("Ungrounded claim", findings[0].explanation)
        self.assertEqual("warn", findings[0].severity)
        self.assertEqual("llm", findings[0].finding_class)
        self.assertEqual("G1-grounding", findings[0].signal_id)

    def test_grounded_claim_produces_no_finding(self):
        model = _make_model("The Earth orbits the Sun.")
        findings = self._run_with_stub(model, ["grounded"])
        self.assertEqual([], findings)

    def test_mixed_claims_only_flags_ungrounded(self):
        # Two-sentence body: first grounded, second ungrounded.
        body = "The Earth orbits the Sun. The moon is made of cheese."
        model = _make_model(body)
        findings = self._run_with_stub(model, ["grounded", "ungrounded"])
        self.assertEqual(1, len(findings))
        self.assertIn("cheese", findings[0].explanation)

    def test_implicated_path_is_set(self):
        model = _make_model("Fake claim here.")
        findings = self._run_with_stub(model, ["ungrounded"])
        self.assertTrue(len(findings[0].implicated) > 0)
        self.assertIn("test.md", findings[0].implicated[0])

    def test_finding_is_instance_of_finding(self):
        model = _make_model("Unverifiable claim.")
        findings = self._run_with_stub(model, ["ungrounded"])
        for finding in findings:
            self.assertIsInstance(finding, Finding)


class GroundingSignalExitStatusTests(unittest.TestCase):
    """Findings must not affect exit status (advisory tier guarantee).

    We verify this at the unit level: run() returning findings should not
    raise any exception; actual validator exit-status testing lives in
    test_eval_framework.py.
    """

    def test_run_with_stub_does_not_raise(self):
        stub = _StubProvider(["ungrounded", "ungrounded"])
        model = _make_model("First claim. Second claim.")
        with patch.object(grounding_mod, "get_provider", return_value=stub):
            try:
                findings = grounding_mod.SIGNAL.run(model)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"run() raised unexpectedly: {exc}")
        self.assertIsInstance(findings, list)

    def test_run_with_disabled_does_not_raise(self):
        model = _make_model("Any text.")
        try:
            findings = grounding_mod.SIGNAL.run(model)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"run() raised unexpectedly with disabled provider: {exc}")
        self.assertIsInstance(findings, list)


if __name__ == "__main__":
    unittest.main()
