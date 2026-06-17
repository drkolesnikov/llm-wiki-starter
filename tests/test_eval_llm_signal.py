"""Tests for tools/eval/llm_signal.py (LLMSignal base class).

Verifies:
- Disabled provider → single "skipped — no backend" Finding (via the base run()).
- Enabled provider → _run_enabled() is called and its findings returned.
- NotImplementedError raised when subclass omits _run_enabled().
- Signal id and finding_class flow through into the skipped Finding correctly.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import tools.eval.llm_signal as llm_signal_mod
from tools.eval import Finding
from tools.eval.llm_signal import LLMSignal
from tools.llm_provider import ModelProvider


# ---------------------------------------------------------------------------
# Stub providers
# ---------------------------------------------------------------------------

class _EnabledProvider(ModelProvider):
    enabled: bool = True

    def complete(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        return "stub response"


class _DisabledProvider(ModelProvider):
    enabled: bool = False

    def complete(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        from tools.llm_provider import ProviderDisabled
        raise ProviderDisabled("no backend")


# ---------------------------------------------------------------------------
# Minimal concrete signals for testing
# ---------------------------------------------------------------------------

class _ConcreteSignal(LLMSignal):
    id = "TEST-signal"
    finding_class = "llm"

    def _run_enabled(self, model, provider) -> list[Finding]:
        return [
            Finding(
                signal_id=self.id,
                finding_class=self.finding_class,
                severity="info",
                implicated=[],
                explanation="enabled path reached",
            )
        ]


class _NotImplementedSignal(LLMSignal):
    id = "TEST-ni"
    finding_class = "llm"
    # intentionally does NOT override _run_enabled


# ---------------------------------------------------------------------------
# Fake model
# ---------------------------------------------------------------------------

class _FakeModel:
    root = Path("/fake")
    artifacts = []
    sources = {}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLLMSignalDisabledGuard(unittest.TestCase):
    """Disabled provider → single skipped Finding, never calls _run_enabled."""

    def setUp(self):
        self.signal = _ConcreteSignal()

    def test_disabled_returns_one_finding(self):
        with patch.object(llm_signal_mod, "get_provider", return_value=_DisabledProvider()):
            findings = self.signal.run(_FakeModel())
        self.assertEqual(1, len(findings))

    def test_disabled_finding_explanation(self):
        with patch.object(llm_signal_mod, "get_provider", return_value=_DisabledProvider()):
            findings = self.signal.run(_FakeModel())
        self.assertIn("skipped", findings[0].explanation)
        self.assertIn("no backend", findings[0].explanation)

    def test_disabled_finding_severity_is_info(self):
        with patch.object(llm_signal_mod, "get_provider", return_value=_DisabledProvider()):
            findings = self.signal.run(_FakeModel())
        self.assertEqual("info", findings[0].severity)

    def test_disabled_finding_uses_signal_id(self):
        with patch.object(llm_signal_mod, "get_provider", return_value=_DisabledProvider()):
            findings = self.signal.run(_FakeModel())
        self.assertEqual("TEST-signal", findings[0].signal_id)

    def test_disabled_finding_uses_finding_class(self):
        with patch.object(llm_signal_mod, "get_provider", return_value=_DisabledProvider()):
            findings = self.signal.run(_FakeModel())
        self.assertEqual("llm", findings[0].finding_class)

    def test_disabled_implicated_is_empty(self):
        with patch.object(llm_signal_mod, "get_provider", return_value=_DisabledProvider()):
            findings = self.signal.run(_FakeModel())
        self.assertEqual([], findings[0].implicated)

    def test_disabled_finding_is_finding_instance(self):
        with patch.object(llm_signal_mod, "get_provider", return_value=_DisabledProvider()):
            findings = self.signal.run(_FakeModel())
        self.assertIsInstance(findings[0], Finding)


class TestLLMSignalEnabledPath(unittest.TestCase):
    """Enabled provider → _run_enabled() is called."""

    def setUp(self):
        self.signal = _ConcreteSignal()

    def test_enabled_returns_run_enabled_findings(self):
        with patch.object(llm_signal_mod, "get_provider", return_value=_EnabledProvider()):
            findings = self.signal.run(_FakeModel())
        self.assertEqual(1, len(findings))
        self.assertEqual("enabled path reached", findings[0].explanation)

    def test_enabled_does_not_return_skipped(self):
        with patch.object(llm_signal_mod, "get_provider", return_value=_EnabledProvider()):
            findings = self.signal.run(_FakeModel())
        for f in findings:
            self.assertNotIn("skipped", f.explanation)


class TestLLMSignalNotImplemented(unittest.TestCase):
    """Subclass that omits _run_enabled raises NotImplementedError when enabled."""

    def test_not_implemented_raises(self):
        signal = _NotImplementedSignal()
        with patch.object(llm_signal_mod, "get_provider", return_value=_EnabledProvider()):
            with self.assertRaises(NotImplementedError):
                signal.run(_FakeModel())


if __name__ == "__main__":
    unittest.main()
