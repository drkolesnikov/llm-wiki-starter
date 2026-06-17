"""Tests for #53: tools/interchange/import_.py OKF v0.1 import + ``import`` command.

Test categories
---------------
- Unit: assemble an OKF bundle fixture with the required edge cases, import into
  a temp staging area, and assert all acceptance criteria from the issue.
- Variant: bundle with no index.md — import succeeds, defect noted.
- CliRunner: ``import`` command, ``--json``, bad-input exits non-zero.
- Auto-discovery: command present without cli.py / __init__.py edits.
"""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import typer
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]

# Make tools/ importable when running from the repo root.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract scalar frontmatter from a staged artifact."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        stripped = line.strip()
        if stripped.startswith("-"):
            continue  # list item
        if ": " in stripped:
            key, _, val = stripped.partition(": ")
            result[key.strip()] = val.strip().strip("\"'")
        elif stripped.endswith(":"):
            pass  # block list header — key only, no scalar value
    return result


# ---------------------------------------------------------------------------
# OKF Bundle fixtures
# ---------------------------------------------------------------------------


def _make_bundle(tmp: Path, include_index: bool = True) -> Path:
    """Build a sample OKF bundle satisfying the fixture requirements.

    Fixture includes:
    - At least 1 unknown ``type`` (``"experimental-note"`` is not in the wiki
      type map).
    - At least 1 missing optional field (``alpha.md`` has no ``description``).
    - At least 1 broken relative link (``beta.md`` links to ``nonexistent.md``).
    - ``include_index=False`` variant omits ``index.md``.
    """
    root = tmp / "bundle"
    root.mkdir()

    # alpha.md: known type, missing optional field (description absent)
    _write(
        root / "alpha.md",
        "\n".join([
            "---",
            "type: knowledge-note",
            "title: Alpha Concept",
            "updated: 2025-01-01",
            "llm-wiki:status: active",
            "llm-wiki:tags:",
            "  - ml",
            "  - ai",
            "custom-extra-key: some-value",
            "---",
            "",
            "# Alpha Concept",
            "",
            "Body of alpha.",
            "",
        ]),
    )

    # beta.md: unknown type + broken relative link
    _write(
        root / "beta.md",
        "\n".join([
            "---",
            "type: experimental-note",
            "title: Beta Experimental",
            "updated: 2025-02-01",
            "description: Beta with broken link.",
            "llm-wiki:status: draft",
            "extra-unknown: preserved-value",
            "---",
            "",
            "# Beta Experimental",
            "",
            "See [missing link](nonexistent.md).",
            "",
        ]),
    )

    # gamma.md: another known type, tests extension key preservation
    _write(
        root / "gamma.md",
        "\n".join([
            "---",
            "type: source-summary",
            "title: Gamma Summary",
            "updated: 2025-03-01",
            "description: Summary of gamma.",
            "resource: https://example.com/gamma",
            "llm-wiki:status: active",
            "llm-wiki:source_count: 5",
            "---",
            "",
            "# Gamma Summary",
            "",
            "Content.",
            "",
        ]),
    )

    if include_index:
        _write(root / "index.md", "# Index\n\nBundle index.\n")

    # log.md should also be skipped (reserved)
    _write(root / "log.md", "# Log\n\n- entry 1\n")

    return root


# ---------------------------------------------------------------------------
# Unit tests: import_bundle
# ---------------------------------------------------------------------------


class TestImportBundleBasic(unittest.TestCase):
    """Assert all acceptance criteria from issue #53."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

        from tools.interchange.import_ import import_bundle
        self._import_bundle = import_bundle

        self.bundle = _make_bundle(self.tmp)
        self.staging = self.tmp / "staging"
        self.result = self._import_bundle(self.bundle, self.staging)

    def tearDown(self):
        self._tmp.cleanup()

    # ------------------------------------------------------------------
    # Counts / basic sanity
    # ------------------------------------------------------------------

    def test_three_artifacts_staged(self):
        """alpha, beta, gamma staged; index.md and log.md skipped."""
        self.assertEqual(self.result.artifacts_staged, 3)

    def test_reserved_files_skipped(self):
        """index.md and log.md count as skipped, not staged."""
        self.assertEqual(self.result.skipped, 2)

    # ------------------------------------------------------------------
    # Status: every artifact must be needs-review, never verified
    # ------------------------------------------------------------------

    def test_every_artifact_status_needs_review(self):
        """All staged artifacts carry status: needs-review."""
        for name in ("alpha.md", "beta.md", "gamma.md"):
            path = self.staging / name
            self.assertTrue(path.exists(), f"{name} not found in staging")
            fm = _parse_frontmatter(path.read_text(encoding="utf-8"))
            self.assertEqual(
                fm.get("status"),
                "needs-review",
                f"{name}: expected status=needs-review, got {fm.get('status')!r}",
            )

    def test_no_artifact_status_verified(self):
        """No staged artifact may carry status: verified."""
        for path in self.staging.rglob("*.md"):
            fm = _parse_frontmatter(path.read_text(encoding="utf-8"))
            self.assertNotEqual(
                fm.get("status"),
                "verified",
                f"{path.name}: found forbidden status=verified",
            )

    # ------------------------------------------------------------------
    # Trusted tree untouched
    # ------------------------------------------------------------------

    def test_only_staging_dir_written(self):
        """No files written outside the staging directory."""
        staging_files = {p for p in self.staging.rglob("*") if p.is_file()}
        # Everything under tmp that isn't under bundle/ or staging/
        all_files = {p for p in self.tmp.rglob("*") if p.is_file()}
        bundle_files = {p for p in self.bundle.rglob("*") if p.is_file()}
        outside = all_files - staging_files - bundle_files
        self.assertEqual(
            outside,
            set(),
            f"Files written outside staging: {outside}",
        )

    # ------------------------------------------------------------------
    # OKF type → artifact_type
    # ------------------------------------------------------------------

    def test_known_type_recorded_as_artifact_type(self):
        """alpha.md: type=knowledge-note becomes artifact_type=knowledge-note."""
        fm = _parse_frontmatter((self.staging / "alpha.md").read_text(encoding="utf-8"))
        self.assertEqual(fm.get("artifact_type"), "knowledge-note")

    def test_unknown_type_recorded_as_artifact_type(self):
        """beta.md: unknown type=experimental-note is still recorded (tolerated)."""
        fm = _parse_frontmatter((self.staging / "beta.md").read_text(encoding="utf-8"))
        self.assertEqual(fm.get("artifact_type"), "experimental-note")

    def test_source_summary_type_recorded(self):
        """gamma.md: type=source-summary → artifact_type=source-summary."""
        fm = _parse_frontmatter((self.staging / "gamma.md").read_text(encoding="utf-8"))
        self.assertEqual(fm.get("artifact_type"), "source-summary")

    # ------------------------------------------------------------------
    # Unknown frontmatter keys preserved
    # ------------------------------------------------------------------

    def test_extension_keys_preserved(self):
        """llm-wiki:status on alpha/beta/gamma preserved verbatim."""
        for name, expected in (
            ("alpha.md", "active"),
            ("beta.md", "draft"),
            ("gamma.md", "active"),
        ):
            fm = _parse_frontmatter((self.staging / name).read_text(encoding="utf-8"))
            self.assertEqual(
                fm.get("llm-wiki:status"),
                expected,
                f"{name}: llm-wiki:status not preserved",
            )

    def test_plain_unknown_key_preserved(self):
        """alpha.md: custom-extra-key is preserved (prefixed or verbatim)."""
        text = (self.staging / "alpha.md").read_text(encoding="utf-8")
        # Key may be stored with okf-preserved: prefix or verbatim
        self.assertTrue(
            "custom-extra-key" in text,
            "custom-extra-key not found in staged alpha.md",
        )

    def test_extra_unknown_key_in_beta_preserved(self):
        """beta.md: extra-unknown key is preserved."""
        text = (self.staging / "beta.md").read_text(encoding="utf-8")
        self.assertTrue(
            "extra-unknown" in text,
            "extra-unknown key not found in staged beta.md",
        )

    # ------------------------------------------------------------------
    # Tolerated defects reported as notes, import not failed
    # ------------------------------------------------------------------

    def test_broken_link_noted_not_failed(self):
        """beta.md has a broken relative link; import completes, note recorded."""
        self.assertGreater(self.result.artifacts_staged, 0, "Import failed unexpectedly")
        broken_notes = [n for n in self.result.notes if "nonexistent.md" in n or "broken" in n]
        self.assertTrue(
            broken_notes,
            f"Expected a note about broken relative link; got notes={self.result.notes}",
        )

    def test_missing_optional_field_tolerated(self):
        """alpha.md has no description — import succeeds, no error raised."""
        # If description is absent in alpha, artifact_type should still be set
        fm = _parse_frontmatter((self.staging / "alpha.md").read_text(encoding="utf-8"))
        self.assertIn("artifact_type", fm, "artifact_type should be set even without description")

    def test_unknown_type_tolerated_not_fatal(self):
        """experimental-note type is unknown but does not fail the import."""
        # Import completed (artifacts_staged > 0) and beta is staged
        self.assertTrue((self.staging / "beta.md").exists())


# ---------------------------------------------------------------------------
# Variant: no index.md
# ---------------------------------------------------------------------------


class TestImportBundleNoIndex(unittest.TestCase):
    """Bundle without index.md — import succeeds, defect noted."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

        from tools.interchange.import_ import import_bundle
        self._import_bundle = import_bundle

        self.bundle = _make_bundle(self.tmp, include_index=False)
        self.staging = self.tmp / "staging"
        self.result = self._import_bundle(self.bundle, self.staging)

    def tearDown(self):
        self._tmp.cleanup()

    def test_import_succeeds_without_index(self):
        """Import does not fail when index.md is absent."""
        self.assertGreater(self.result.artifacts_staged, 0)

    def test_missing_index_reported_as_note(self):
        """A note about missing index.md is recorded."""
        index_notes = [n for n in self.result.notes if "index.md" in n]
        self.assertTrue(
            index_notes,
            f"Expected note about missing index.md; got notes={self.result.notes}",
        )

    def test_all_staged_still_needs_review(self):
        """Even without index.md all staged artifacts are needs-review."""
        for path in self.staging.rglob("*.md"):
            fm = _parse_frontmatter(path.read_text(encoding="utf-8"))
            self.assertEqual(fm.get("status"), "needs-review")


# ---------------------------------------------------------------------------
# No-overwrite guarantee
# ---------------------------------------------------------------------------


class TestImportNoOverwrite(unittest.TestCase):
    """Pre-existing staging files are never overwritten."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

        from tools.interchange.import_ import import_bundle
        self._import_bundle = import_bundle

    def tearDown(self):
        self._tmp.cleanup()

    def test_existing_staging_file_not_overwritten(self):
        """Pre-existing file in staging is kept; a note is emitted."""
        bundle = _make_bundle(self.tmp)
        staging = self.tmp / "staging"

        # First import
        self._import_bundle(bundle, staging)
        # Record original content of alpha.md
        orig_text = (staging / "alpha.md").read_text(encoding="utf-8")

        # Modify bundle alpha.md
        (bundle / "alpha.md").write_text(
            "---\ntype: knowledge-note\ntitle: Alpha Modified\n---\n\nModified.\n",
            encoding="utf-8",
        )

        # Second import — must not overwrite
        result2 = self._import_bundle(bundle, staging)
        current_text = (staging / "alpha.md").read_text(encoding="utf-8")
        self.assertEqual(orig_text, current_text, "Staging file was overwritten")
        skip_notes = [n for n in result2.notes if "alpha.md" in n and "overwrite" in n.lower()]
        self.assertTrue(skip_notes, f"Expected no-overwrite note; got {result2.notes}")


# ---------------------------------------------------------------------------
# Bad bundle path
# ---------------------------------------------------------------------------


class TestImportBadPath(unittest.TestCase):
    """Non-existent bundle path returns empty result with a note."""

    def test_nonexistent_bundle_path(self):
        from tools.interchange.import_ import import_bundle
        with tempfile.TemporaryDirectory() as td:
            result = import_bundle(Path(td) / "does_not_exist", Path(td) / "staging")
            self.assertEqual(result.artifacts_staged, 0)
            self.assertTrue(result.notes, "Expected at least one note for bad bundle path")


# ---------------------------------------------------------------------------
# CliRunner: ``import`` command
# ---------------------------------------------------------------------------


class TestImportCommand(unittest.TestCase):
    """CLI integration tests for the auto-discovered ``import`` command."""

    def _make_app(self) -> typer.Typer:
        """Build a Typer app with commands auto-discovered from commands/."""
        from llm_wiki_wizard.commands import register_all
        app = typer.Typer(name="wiki")
        register_all(app)
        return app

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.runner = CliRunner()

    def tearDown(self):
        self._tmp.cleanup()

    def test_import_command_registered(self):
        """``import`` command is auto-discovered — no cli.py / __init__.py edit."""
        app = self._make_app()
        cmd_names = [c.name for c in app.registered_commands]
        self.assertIn("import", cmd_names, f"import command not found; available: {cmd_names}")

    def test_import_json_output(self):
        """``import --json`` emits valid JSON with artifacts_staged key."""
        bundle = _make_bundle(self.tmp)
        staging = self.tmp / "staging"
        app = self._make_app()
        result = self.runner.invoke(
            app,
            ["import", str(bundle), "--staging", str(staging), "--json"],
        )
        self.assertEqual(result.exit_code, 0, f"Non-zero exit: {result.output}")
        data = json.loads(result.output)
        self.assertIn("artifacts_staged", data)
        self.assertGreater(data["artifacts_staged"], 0)
        self.assertIn("notes", data)
        self.assertIn("skipped", data)

    def test_import_bad_bundle_exits_nonzero(self):
        """Bad bundle path → non-zero exit with structured JSON error."""
        staging = self.tmp / "staging"
        app = self._make_app()
        result = self.runner.invoke(
            app,
            ["import", str(self.tmp / "no_such_bundle"), "--staging", str(staging), "--json"],
        )
        self.assertNotEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertIn("error", data)

    def test_import_missing_staging_arg_exits_nonzero(self):
        """Missing required --staging argument → non-zero exit."""
        bundle = _make_bundle(self.tmp)
        app = self._make_app()
        result = self.runner.invoke(app, ["import", str(bundle)])
        self.assertNotEqual(result.exit_code, 0)


# ---------------------------------------------------------------------------
# Auto-discovery: command module registers without cli.py edits
# ---------------------------------------------------------------------------


class TestAutoDiscovery(unittest.TestCase):
    """Ensure okf_import.py is picked up by the auto-discovery loader."""

    def test_module_exposes_register(self):
        """llm_wiki_wizard.commands.okf_import exposes a callable register."""
        module = importlib.import_module("llm_wiki_wizard.commands.okf_import")
        register = getattr(module, "register", None)
        self.assertTrue(callable(register), "okf_import.register is not callable")

    def test_import_symbol_in_interchange(self):
        """tools.interchange exposes import_bundle and ImportResult."""
        from tools.interchange import ImportResult, import_bundle  # noqa: F401
        self.assertTrue(callable(import_bundle))
        self.assertTrue(isinstance(ImportResult(), ImportResult))


if __name__ == "__main__":
    unittest.main()
