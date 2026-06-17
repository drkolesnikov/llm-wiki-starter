import importlib
import subprocess
import sys
import unittest
from pathlib import Path

from tools import eval as eval_pkg
from tools.eval import Finding, Signal, render_report, run_suite
from tools.wiki_model import load_repo_model


ROOT = Path(__file__).resolve().parents[1]
SIGNALS_DIR = ROOT / "tools" / "eval" / "signals"


class _StubSignal:
    """A minimal deterministic signal used as a discovery probe."""

    id = "zz99-probe"
    finding_class = "deterministic"

    def run(self, model):  # noqa: ARG002 - model is intentionally unused
        return [Finding(self.id, self.finding_class, "info", ["probe.md"], "probe finding")]


class FindingAndReportTests(unittest.TestCase):
    def test_finding_is_immutable_and_serialisable(self):
        finding = Finding("sig", "deterministic", "warn", ["a.md", "b.md"], "why")
        with self.assertRaises(Exception):
            finding.signal_id = "other"  # frozen dataclass
        self.assertEqual(
            {
                "signal_id": "sig",
                "finding_class": "deterministic",
                "severity": "warn",
                "implicated": ["a.md", "b.md"],
                "explanation": "why",
            },
            finding.as_dict(),
        )

    def test_render_report_empty(self):
        markdown, machine = render_report([])
        self.assertIn("No findings.", markdown)
        self.assertEqual(0, machine["total"])
        self.assertEqual({"deterministic": 0, "llm": 0}, machine["counts"])
        self.assertEqual([], machine["findings"])

    def test_render_report_with_findings(self):
        findings = [
            Finding("a", "deterministic", "info", ["x.md"], "ex-a"),
            Finding("b", "llm", "warn", [], "ex-b"),
        ]
        markdown, machine = render_report(findings)
        self.assertIn("**a**", markdown)
        self.assertIn("ex-b", markdown)
        self.assertEqual(2, machine["total"])
        self.assertEqual({"deterministic": 1, "llm": 1}, machine["counts"])


class SignalRegistryTests(unittest.TestCase):
    def test_discovered_signals_conform_and_have_unique_ids(self):
        # Holds whether the signals package is empty (issue #35) or populated
        # (issue #20): every discovered signal conforms to the protocol and
        # carries a unique id. (Replaces the old "dir is empty" assertion, which
        # was only true before the signal slices landed.)
        discovered = eval_pkg.discover_signals()
        ids = []
        for _name, signal in discovered:
            self.assertIsInstance(signal, Signal)
            self.assertIn(signal.finding_class, ("deterministic", "llm"))
            ids.append(signal.id)
        self.assertEqual(len(ids), len(set(ids)), "signal ids must be unique")

    def test_suite_returns_only_findings(self):
        model = load_repo_model(ROOT)
        for finding in run_suite(model):
            self.assertIsInstance(finding, Finding)

    def test_stub_satisfies_signal_protocol(self):
        self.assertIsInstance(_StubSignal(), Signal)


class SignalDiscoveryTests(unittest.TestCase):
    """A signal is add-a-file: dropping a module exposing SIGNAL into
    tools/eval/signals/ is discovered and run with no edit to tools/eval."""

    def test_dropped_signal_is_discovered_and_run(self):
        marker = "zz99_probe_signal"
        probe_path = SIGNALS_DIR / f"{marker}.py"
        probe_path.write_text(
            "try:\n"
            "    from tools.eval import Finding\n"
            "except ImportError:\n"
            "    from eval import Finding\n"
            "\n"
            "\n"
            "class _Probe:\n"
            "    id = 'zz99-probe'\n"
            "    finding_class = 'deterministic'\n"
            "\n"
            "    def run(self, model):\n"
            "        return [Finding(self.id, self.finding_class, 'info', [], 'probe')]\n"
            "\n"
            "\n"
            "SIGNAL = _Probe()\n",
            encoding="utf-8",
        )
        try:
            importlib.invalidate_caches()
            discovered = dict(eval_pkg.discover_signals())
            self.assertIn(marker, discovered, "new signal module not auto-discovered")
            # It sorts last given the 'zz99' prefix.
            self.assertEqual(list(discovered)[-1], marker)

            model = load_repo_model(ROOT)
            findings = run_suite(model)
            self.assertEqual(1, len(findings))
            self.assertEqual("zz99-probe", findings[0].signal_id)
            self.assertEqual("probe", findings[0].explanation)

            # Selection by id is honoured: an unrelated id selects nothing.
            self.assertEqual([], run_suite(model, selected=["does-not-exist"]))
            self.assertEqual(1, len(run_suite(model, selected=["zz99-probe"])))
        finally:
            probe_path.unlink(missing_ok=True)
            sys.modules.pop(f"tools.eval.signals.{marker}", None)
            sys.modules.pop(f"eval.signals.{marker}", None)
            importlib.invalidate_caches()


class ExitStatusUnaffectedTests(unittest.TestCase):
    """Eval findings are advisory: even when a signal produces findings, the
    advisory-health tier surfaces them and the exit status stays 0."""

    def test_health_tier_exit_status_unaffected_by_findings(self):
        marker = "zz99_probe_exit"
        probe_path = SIGNALS_DIR / f"{marker}.py"
        probe_path.write_text(
            "try:\n"
            "    from tools.eval import Finding\n"
            "except ImportError:\n"
            "    from eval import Finding\n"
            "\n"
            "\n"
            "class _Probe:\n"
            "    id = 'zz99-exit-probe'\n"
            "    finding_class = 'deterministic'\n"
            "\n"
            "    def run(self, model):\n"
            "        return [Finding(self.id, self.finding_class, 'warn', ['x.md'], 'advisory only')]\n"
            "\n"
            "\n"
            "SIGNAL = _Probe()\n",
            encoding="utf-8",
        )
        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "validate_repo.py"), "--tier", "health"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("[tier: advisory-health]", result.stdout)
            self.assertIn("Evaluation report", result.stdout)
            # The dropped signal's finding surfaces under the health tier.
            self.assertIn("zz99-exit-probe", result.stdout)
            self.assertIn("advisory only", result.stdout)
        finally:
            probe_path.unlink(missing_ok=True)
            importlib.invalidate_caches()

    def test_default_invocation_exit_status_unchanged(self):
        # The default (no --tier) path never runs the eval suite and stays 0.
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "validate_repo.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("Evaluation report", result.stdout)


if __name__ == "__main__":
    unittest.main()
