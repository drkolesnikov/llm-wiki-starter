import importlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tools import validate_repo


ROOT = Path(__file__).resolve().parents[1]
CHECKS_DIR = ROOT / "tools" / "checks"


def _write_durable_note(root: Path, name: str, body_lines: list[str]) -> None:
    (root / "knowledge").mkdir(exist_ok=True)
    (root / "knowledge" / name).write_text("\n".join(body_lines) + "\n", encoding="utf-8")


class DefaultTierUnchangedTests(unittest.TestCase):
    """The default (no --tier) invocation must stay byte-identical to today."""

    def test_default_invocation_passes_without_tier_label(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "validate_repo.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Repository validation passed.", result.stdout)
        # No tier selected => no tier banner, preserving legacy output exactly.
        self.assertNotIn("[tier:", result.stdout)

    def test_default_health_report_flag_still_works(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "validate_repo.py"), "--health-report"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Repository validation passed.", result.stdout)
        self.assertIn("Wiki health report", result.stdout)
        self.assertNotIn("[tier:", result.stdout)


class TierInvocationTests(unittest.TestCase):
    """Each tier is independently invocable and labels its own output."""

    def _run(self, *tiers: str):
        argv = [sys.executable, str(ROOT / "tools" / "validate_repo.py")]
        for tier in tiers:
            argv += ["--tier", tier]
        return subprocess.run(
            argv, cwd=ROOT, text=True, capture_output=True, check=False
        )

    def test_structural_tier_labeled_and_blocking_pass(self):
        result = self._run("structural")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("[tier: structural]", result.stdout)
        self.assertIn("Repository validation passed.", result.stdout)

    def test_portable_tier_labeled(self):
        result = self._run("portable")
        self.assertIn("[tier: portable-profile]", result.stdout)
        self.assertIn("Portable-profile report", result.stdout)

    def test_health_tier_labeled_and_non_blocking(self):
        result = self._run("health")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("[tier: advisory-health]", result.stdout)
        self.assertIn("Wiki health report", result.stdout)

    def test_all_three_tiers_run_in_stable_order(self):
        result = self._run("health", "portable", "structural")
        banners = [
            line for line in result.stdout.splitlines() if line.startswith("[tier:")
        ]
        self.assertEqual(
            ["[tier: structural]", "[tier: portable-profile]", "[tier: advisory-health]"],
            banners,
        )


class PortableProfileRuleTests(unittest.TestCase):
    """Portable profile: fail on artifact_type/title/valid-updated; advise on
    description/resource (issue #30 rule)."""

    def test_passes_with_required_trio_and_advises_recommended(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_durable_note(
                root,
                "ok.md",
                [
                    "---",
                    "artifact_type: knowledge-note",
                    "status: active",
                    'title: "Has Required Trio"',
                    "updated: 2025-11-03",
                    "---",
                    "# Has Required Trio",
                ],
            )
            with mock.patch.object(validate_repo, "ROOT", root):
                report, failures = validate_repo.portable_profile_report()
            self.assertEqual(0, failures, report)
            # description/resource are missing but only advised, never failed.
            self.assertIn("missing recommended core field 'description'", report)
            self.assertIn("missing recommended core field 'resource'", report)

    def test_missing_title_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_durable_note(
                root,
                "notitle.md",
                [
                    "---",
                    "artifact_type: knowledge-note",
                    "status: active",
                    "updated: 2025-11-03",
                    "---",
                    "# Body",
                ],
            )
            with mock.patch.object(validate_repo, "ROOT", root):
                report, failures = validate_repo.portable_profile_report()
            self.assertEqual(1, failures, report)
            self.assertIn("missing portable-core field 'title'", report)

    def test_non_iso_updated_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_durable_note(
                root,
                "baddate.md",
                [
                    "---",
                    "artifact_type: knowledge-note",
                    "status: active",
                    'title: "Bad Date"',
                    "updated: November 3 2025",
                    "---",
                    "# Bad Date",
                ],
            )
            with mock.patch.object(validate_repo, "ROOT", root):
                report, failures = validate_repo.portable_profile_report()
            self.assertEqual(1, failures, report)
            self.assertIn("not an ISO-8601", report)

    def test_valid_iso_date_helper(self):
        self.assertTrue(validate_repo.valid_iso_date("2025-11-03"))
        self.assertFalse(validate_repo.valid_iso_date("2025/11/03"))
        self.assertFalse(validate_repo.valid_iso_date("2025-1-3"))
        self.assertFalse(validate_repo.valid_iso_date(None))
        self.assertFalse(validate_repo.valid_iso_date(""))


class ChecksAutoDiscoveryTests(unittest.TestCase):
    """A new structural check is add-a-file: dropping a module into
    tools/checks/ is picked up with zero edits to validate_repo.py."""

    def test_checks_discovered_in_sorted_filename_order(self):
        try:
            from tools import checks
        except ImportError:  # pragma: no cover - script-style fallback
            sys.path.insert(0, str(ROOT / "tools"))
            import checks  # type: ignore
        names = [name for name, _ in checks.discover_checks()]
        self.assertEqual(names, sorted(names))
        # The three Wave-0/issue-30 structural checks are present and ordered.
        self.assertIn("c10_frontmatter", names)
        self.assertIn("c20_registry", names)
        self.assertIn("c30_links", names)

    def test_dropping_a_new_module_adds_a_check_without_editing_validator(self):
        from tools import checks

        marker = "zz99_probe_addfile"
        probe_path = CHECKS_DIR / f"{marker}.py"
        probe_path.write_text(
            "MARK = '#30-probe'\n"
            "def check(model, errors):\n"
            "    errors.append(MARK)\n",
            encoding="utf-8",
        )
        try:
            importlib.invalidate_caches()
            discovered = dict(checks.discover_checks())
            self.assertIn(marker, discovered, "new module not auto-discovered")
            # It must sort last given the 'zz99' prefix.
            self.assertEqual(list(discovered)[-1], marker)
            # And the discovered callable actually runs and appends its error,
            # proving the registry wires new modules in with zero validator edits.
            errors: list[str] = []
            discovered[marker](None, errors)
            self.assertIn("#30-probe", errors)
        finally:
            probe_path.unlink(missing_ok=True)
            sys.modules.pop(f"tools.checks.{marker}", None)
            sys.modules.pop(f"checks.{marker}", None)
            importlib.invalidate_caches()


if __name__ == "__main__":
    unittest.main()
