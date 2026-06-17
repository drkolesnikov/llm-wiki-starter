"""Tests for tools/eval/signals/contradiction.py (G3-contradiction signal).

Uses unittest exclusively (no pytest).  The LLM provider is always stubbed via
``unittest.mock.patch`` so no real backend is required and tests are fast and
deterministic.
"""

from __future__ import annotations

import sys
import os
import unittest
from pathlib import Path
from unittest import mock

# Ensure repo root is importable as a package root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.eval import Finding
from tools.eval.signals import contradiction as _mod
from tools.llm_provider import DisabledProvider, ModelProvider


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

class _EnabledStubProvider(ModelProvider):
    """A minimal enabled provider whose responses can be configured per test."""

    enabled: bool = True

    def __init__(self, responses: dict[str, str] | None = None):
        # responses maps (fragment of) prompt → response; default is "OK".
        self._responses: dict[str, str] = responses or {}
        self.calls: list[str] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls.append(prompt)
        for key, response in self._responses.items():
            if key in prompt:
                return response
        return "OK"


def _stub_artifact(path_str: str, artifact_type: str, body: str, source: str | None = None):
    """Return a minimal Artifact-like object."""
    from tools.wiki_model import Artifact
    fm: dict = {"artifact_type": artifact_type}
    if source:
        fm["source"] = source
    return Artifact(path=Path(path_str), frontmatter=fm, body=body)


def _stub_model(artifacts=None, sources=None):
    """Return a minimal RepoModel-like object."""
    from tools.wiki_model import RepoModel
    return RepoModel(
        root=_REPO_ROOT,
        artifacts=artifacts or [],
        sources=sources or {},
    )


# ---------------------------------------------------------------------------
# Tests: disabled provider
# ---------------------------------------------------------------------------

class TestDisabledProvider(unittest.TestCase):
    """When get_provider() returns a disabled provider, run() returns a single
    'skipped — no backend' Finding without raising."""

    def test_skipped_finding_returned(self):
        disabled = DisabledProvider()
        with mock.patch.object(_mod, "get_provider", return_value=disabled):
            findings = _mod.SIGNAL.run(_stub_model())
        self.assertEqual(1, len(findings))
        finding = findings[0]
        self.assertIsInstance(finding, Finding)
        self.assertEqual("G3-contradiction", finding.signal_id)
        self.assertEqual("llm", finding.finding_class)
        self.assertIn("skipped", finding.explanation)
        self.assertIn("no backend", finding.explanation)

    def test_skipped_finding_severity_is_info(self):
        disabled = DisabledProvider()
        with mock.patch.object(_mod, "get_provider", return_value=disabled):
            findings = _mod.SIGNAL.run(_stub_model())
        self.assertEqual("info", findings[0].severity)

    def test_skipped_implicated_is_empty(self):
        disabled = DisabledProvider()
        with mock.patch.object(_mod, "get_provider", return_value=disabled):
            findings = _mod.SIGNAL.run(_stub_model())
        self.assertEqual([], findings[0].implicated)


# ---------------------------------------------------------------------------
# Tests: enabled provider, contradiction detection
# ---------------------------------------------------------------------------

class TestContradictionDetection(unittest.TestCase):
    """With an enabled stub provider that returns CONTRADICTION for a known
    pair, a finding is produced and shaped for the 'conflicted' status."""

    def _provider_for_contradiction(self, key: str = "", reason: str = "claims differ") -> _EnabledStubProvider:
        return _EnabledStubProvider(responses={key: f"CONTRADICTION: {reason}"})

    def test_artifact_vs_artifact_contradiction_produces_finding(self):
        art_a = _stub_artifact("notes/a.md", "knowledge-note", "The sky is green.")
        art_b = _stub_artifact("notes/b.md", "knowledge-note", "The sky is blue.")
        model = _stub_model(artifacts=[art_a, art_b])
        provider = _EnabledStubProvider(responses={"": "CONTRADICTION: sky colour mismatch"})
        with mock.patch.object(_mod, "get_provider", return_value=provider):
            findings = _mod.SIGNAL.run(model)
        self.assertGreater(len(findings), 0)
        finding = findings[0]
        self.assertEqual("G3-contradiction", finding.signal_id)
        self.assertEqual("llm", finding.finding_class)
        self.assertEqual("warn", finding.severity)

    def test_finding_maps_onto_conflicted_status(self):
        """Explanation must mention 'conflicted' so reviewers/agents know which
        governance status to apply."""
        art_a = _stub_artifact("notes/a.md", "knowledge-note", "X is true.")
        art_b = _stub_artifact("notes/b.md", "knowledge-note", "X is false.")
        model = _stub_model(artifacts=[art_a, art_b])
        provider = _EnabledStubProvider(responses={"": "CONTRADICTION: direct negation"})
        with mock.patch.object(_mod, "get_provider", return_value=provider):
            findings = _mod.SIGNAL.run(model)
        self.assertTrue(
            any("conflicted" in f.explanation for f in findings),
            "At least one finding must reference 'conflicted' status",
        )

    def test_no_findings_when_provider_says_ok(self):
        art_a = _stub_artifact("notes/a.md", "knowledge-note", "Paris is the capital of France.")
        art_b = _stub_artifact("notes/b.md", "knowledge-note", "Berlin is the capital of Germany.")
        model = _stub_model(artifacts=[art_a, art_b])
        provider = _EnabledStubProvider()  # always returns "OK"
        with mock.patch.object(_mod, "get_provider", return_value=provider):
            findings = _mod.SIGNAL.run(model)
        self.assertEqual([], findings)

    def test_non_checkable_artifact_types_are_ignored(self):
        """Only knowledge-note and source-summary are checked; other types skip."""
        art = _stub_artifact("notes/a.md", "index", "some content")
        art2 = _stub_artifact("notes/b.md", "log", "other content")
        model = _stub_model(artifacts=[art, art2])
        provider = _EnabledStubProvider(responses={"": "CONTRADICTION: should not appear"})
        with mock.patch.object(_mod, "get_provider", return_value=provider):
            findings = _mod.SIGNAL.run(model)
        self.assertEqual([], findings)

    def test_artifact_vs_source_contradiction_produces_finding(self):
        art = _stub_artifact("notes/n.md", "knowledge-note", "Water boils at 50 C.", source="ref-water")
        sources = {"ref-water": {"description": "Water boils at 100 degrees Celsius at standard pressure."}}
        model = _stub_model(artifacts=[art], sources=sources)
        provider = _EnabledStubProvider(responses={"": "CONTRADICTION: temperature mismatch"})
        with mock.patch.object(_mod, "get_provider", return_value=provider):
            findings = _mod.SIGNAL.run(model)
        self.assertGreater(len(findings), 0)
        self.assertTrue(
            any("conflicted" in f.explanation for f in findings),
            "Artifact-vs-source finding must reference 'conflicted' status",
        )

    def test_artifact_vs_source_ok_produces_no_finding(self):
        art = _stub_artifact("notes/n.md", "knowledge-note", "Water boils at 100 C.", source="ref-water")
        sources = {"ref-water": {"description": "Water boils at 100 degrees Celsius."}}
        model = _stub_model(artifacts=[art], sources=sources)
        provider = _EnabledStubProvider()  # always OK
        with mock.patch.object(_mod, "get_provider", return_value=provider):
            findings = _mod.SIGNAL.run(model)
        self.assertEqual([], findings)

    def test_artifact_without_source_key_skips_source_check(self):
        art = _stub_artifact("notes/n.md", "knowledge-note", "Some claim.")
        sources = {"ref": {"description": "Different content."}}
        model = _stub_model(artifacts=[art], sources=sources)
        provider = _EnabledStubProvider(responses={"": "CONTRADICTION: should not be reached"})
        with mock.patch.object(_mod, "get_provider", return_value=provider):
            # No artifact has a 'source' frontmatter key, so provider is never called for vs-source.
            # The single-artifact model also means no vs-artifact calls.
            findings = _mod.SIGNAL.run(model)
        self.assertEqual([], findings)

    def test_implicated_contains_artifact_paths_for_artifact_vs_artifact(self):
        art_a = _stub_artifact("notes/a.md", "knowledge-note", "claim A")
        art_b = _stub_artifact("notes/b.md", "knowledge-note", "claim B")
        model = _stub_model(artifacts=[art_a, art_b])
        provider = _EnabledStubProvider(responses={"": "CONTRADICTION: reason"})
        with mock.patch.object(_mod, "get_provider", return_value=provider):
            findings = _mod.SIGNAL.run(model)
        self.assertGreater(len(findings), 0)
        implicated = findings[0].implicated
        self.assertTrue(
            any("a.md" in p for p in implicated),
            "Implicated should contain path to artifact A",
        )
        self.assertTrue(
            any("b.md" in p for p in implicated),
            "Implicated should contain path to artifact B",
        )


# ---------------------------------------------------------------------------
# Tests: signal protocol conformance
# ---------------------------------------------------------------------------

class TestSignalProtocolConformance(unittest.TestCase):
    def test_signal_id(self):
        self.assertEqual("G3-contradiction", _mod.SIGNAL.id)

    def test_finding_class(self):
        self.assertEqual("llm", _mod.SIGNAL.finding_class)

    def test_satisfies_signal_protocol(self):
        from tools.eval import Signal
        self.assertIsInstance(_mod.SIGNAL, Signal)

    def test_run_returns_list(self):
        disabled = DisabledProvider()
        with mock.patch.object(_mod, "get_provider", return_value=disabled):
            result = _mod.SIGNAL.run(_stub_model())
        self.assertIsInstance(result, list)

    def test_all_returned_items_are_findings(self):
        disabled = DisabledProvider()
        with mock.patch.object(_mod, "get_provider", return_value=disabled):
            result = _mod.SIGNAL.run(_stub_model())
        for item in result:
            self.assertIsInstance(item, Finding)


# ---------------------------------------------------------------------------
# Tests: auto-discovery integration
# ---------------------------------------------------------------------------

class TestAutoDiscovery(unittest.TestCase):
    """The signal must be auto-discovered by tools.eval.discover_signals()."""

    def test_contradiction_signal_is_discovered(self):
        import importlib
        import tools.eval as eval_pkg
        importlib.invalidate_caches()
        discovered = dict(eval_pkg.discover_signals())
        self.assertIn("contradiction", discovered, "contradiction module not discovered")

    def test_discovered_signal_has_correct_id(self):
        import importlib
        import tools.eval as eval_pkg
        importlib.invalidate_caches()
        discovered = dict(eval_pkg.discover_signals())
        if "contradiction" in discovered:
            self.assertEqual("G3-contradiction", discovered["contradiction"].id)


if __name__ == "__main__":
    unittest.main()
