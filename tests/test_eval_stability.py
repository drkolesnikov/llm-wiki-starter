"""Tests for tools/eval/signals/stability.py (G7-stability signal).

Coverage:
- Substantive drift is reported as a Finding.
- Cosmetic churn is NOT reported (no Finding).
- Disabled provider → single "skipped — no backend" Finding.
- Signal is auto-discoverable by the framework.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.eval import Finding, Signal  # noqa: E402
from tools.llm_provider import ModelProvider  # noqa: E402
from tools.wiki_model import Artifact, RepoModel  # noqa: E402


# ---------------------------------------------------------------------------
# Stub provider helpers
# ---------------------------------------------------------------------------

class _SubstantiveProvider(ModelProvider):
    """Always judges changes as SUBSTANTIVE."""

    enabled: bool = True

    def complete(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        return "SUBSTANTIVE\nThe article now omits a key definition present in the prior version."


class _CosmeticProvider(ModelProvider):
    """Always judges changes as COSMETIC."""

    enabled: bool = True

    def complete(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        return "COSMETIC\nOnly whitespace was adjusted."


class _DisabledProvider(ModelProvider):
    """Simulates a disabled (no-backend) provider."""

    enabled: bool = False

    def complete(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        from tools.llm_provider import ProviderDisabled
        raise ProviderDisabled("no backend")


# ---------------------------------------------------------------------------
# Fake repo model helpers
# ---------------------------------------------------------------------------

def _make_artifact(tmp_path: Path, name: str, content: str) -> Artifact:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return Artifact(path=p, frontmatter={}, body=content)


def _make_model(tmp_path: Path, artifacts: list[Artifact]) -> RepoModel:
    return RepoModel(root=tmp_path, artifacts=artifacts, sources={})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStabilitySignalMetadata(unittest.TestCase):
    """Signal has the correct id and finding_class."""

    def setUp(self):
        from tools.eval.signals.stability import SIGNAL
        self.signal = SIGNAL

    def test_signal_id(self):
        self.assertEqual("G7-stability", self.signal.id)

    def test_signal_finding_class(self):
        self.assertEqual("llm", self.signal.finding_class)

    def test_signal_satisfies_protocol(self):
        self.assertIsInstance(self.signal, Signal)


class TestStabilitySignalDisabled(unittest.TestCase):
    """Disabled provider → single 'skipped — no backend' Finding."""

    def setUp(self):
        from tools.eval.signals.stability import SIGNAL
        self.signal = SIGNAL

    def test_disabled_returns_single_skipped_finding(self):
        with mock.patch("tools.eval.signals.stability.get_provider", return_value=_DisabledProvider()):
            model = _make_model(Path("/tmp"), [])
            findings = self.signal.run(model)

        self.assertEqual(1, len(findings))
        f = findings[0]
        self.assertIsInstance(f, Finding)
        self.assertEqual("G7-stability", f.signal_id)
        self.assertEqual("llm", f.finding_class)
        self.assertIn("skipped", f.explanation)
        self.assertIn("no backend", f.explanation)

    def test_disabled_finding_severity_is_info(self):
        with mock.patch("tools.eval.signals.stability.get_provider", return_value=_DisabledProvider()):
            model = _make_model(Path("/tmp"), [])
            findings = self.signal.run(model)

        self.assertEqual("info", findings[0].severity)


class TestStabilitySignalSubstantiveDrift(unittest.TestCase):
    """Substantive drift (provider says SUBSTANTIVE) produces a Finding."""

    def setUp(self):
        from tools.eval.signals.stability import SIGNAL
        self.signal = SIGNAL

    def _run_with_prior(self, tmp_path: Path, current_content: str, prior_content: str):
        artifact = _make_artifact(tmp_path, "notes.md", current_content)
        model = _make_model(tmp_path, [artifact])
        with (
            mock.patch("tools.eval.signals.stability.get_provider", return_value=_SubstantiveProvider()),
            mock.patch(
                "tools.eval.signals.stability._git_show_prior",
                return_value=prior_content,
            ),
        ):
            return self.signal.run(model)

    def test_substantive_drift_produces_finding(self, tmp_path=None):
        if tmp_path is None:
            import tempfile
            with tempfile.TemporaryDirectory() as d:
                return self.test_substantive_drift_produces_finding(tmp_path=Path(d))
        findings = self._run_with_prior(
            tmp_path,
            current_content="# Article\n\nCompletely different content now.",
            prior_content="# Article\n\nOriginal content with key definition.",
        )
        self.assertEqual(1, len(findings))
        f = findings[0]
        self.assertEqual("G7-stability", f.signal_id)
        self.assertEqual("llm", f.finding_class)
        self.assertEqual("warn", f.severity)
        self.assertIn("notes.md", f.implicated[0])

    def test_substantive_finding_has_explanation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            findings = self._run_with_prior(
                tmp,
                current_content="# Article\n\nNew.",
                prior_content="# Article\n\nOld.",
            )
        self.assertTrue(findings[0].explanation)


class TestStabilitySignalCosmeticChurn(unittest.TestCase):
    """Cosmetic churn (provider says COSMETIC) produces NO finding."""

    def setUp(self):
        from tools.eval.signals.stability import SIGNAL
        self.signal = SIGNAL

    def test_cosmetic_churn_not_reported(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            artifact = _make_artifact(tmp, "notes.md", "# Article\n\nSame content.\n")
            model = _make_model(tmp, [artifact])
            with (
                mock.patch("tools.eval.signals.stability.get_provider", return_value=_CosmeticProvider()),
                mock.patch(
                    "tools.eval.signals.stability._git_show_prior",
                    return_value="# Article\n\nSame content.  ",  # trailing space = cosmetic
                ),
            ):
                findings = self.signal.run(model)

        self.assertEqual([], findings)


class TestStabilitySignalNoChanges(unittest.TestCase):
    """Identical current and prior texts → no finding (no provider call needed)."""

    def setUp(self):
        from tools.eval.signals.stability import SIGNAL
        self.signal = SIGNAL

    def test_identical_texts_produce_no_finding(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            content = "# Article\n\nUnchanged.\n"
            artifact = _make_artifact(tmp, "notes.md", content)
            model = _make_model(tmp, [artifact])
            with (
                mock.patch("tools.eval.signals.stability.get_provider", return_value=_SubstantiveProvider()),
                mock.patch(
                    "tools.eval.signals.stability._git_show_prior",
                    return_value=content,  # same as current → no diff
                ),
            ):
                findings = self.signal.run(model)

        self.assertEqual([], findings)

    def test_new_file_no_prior_produces_no_finding(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            artifact = _make_artifact(tmp, "new.md", "# New file\n")
            model = _make_model(tmp, [artifact])
            with (
                mock.patch("tools.eval.signals.stability.get_provider", return_value=_SubstantiveProvider()),
                mock.patch(
                    "tools.eval.signals.stability._git_show_prior",
                    return_value=None,  # no prior → skip
                ),
            ):
                findings = self.signal.run(model)

        self.assertEqual([], findings)


class TestStabilitySignalDiscovery(unittest.TestCase):
    """Signal is auto-discovered by the eval framework."""

    def test_signal_is_discovered(self):
        import importlib
        from tools import eval as eval_pkg
        importlib.invalidate_caches()
        discovered = dict(eval_pkg.discover_signals())
        self.assertIn("stability", discovered)
        self.assertEqual("G7-stability", discovered["stability"].id)


if __name__ == "__main__":
    unittest.main()
