"""Tests for #37: tools/generate_indexes.py + ``index``/``reindex`` commands.

Test categories
---------------
- Unit: temp-wiki fixture covering all acceptance criteria from the issue.
- CliRunner: ``index`` and ``reindex`` commands, ``--dry-run``, ``--json``.
- Validator: structural validator passes after generation.
"""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers to build temp wikis
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _artifact(title: str, status: str = "active", description: str = "", extra: str = "") -> str:
    fm_lines = [
        "---",
        "artifact_type: knowledge-note",
        f'title: "{title}"',
        f"status: {status}",
    ]
    if description:
        fm_lines.append(f'description: "{description}"')
    if extra:
        fm_lines.append(extra)
    fm_lines += ["---", "", f"# {title}", "", "## Claim", "", "A test claim.", ""]
    return "\n".join(fm_lines)


def _minimal_wiki(tmp: Path) -> Path:
    """Create a minimal governed wiki under *tmp* and return its root."""
    root = tmp / "wiki"
    root.mkdir()

    # meta/ — required by validator
    (root / "meta").mkdir()
    _write(root / "meta" / "source-registry.md", (
        "---\nartifact_type: source-registry\nstatus: active\n---\n\n"
        "# Source Registry\n\n"
        "| Source ID | Title | Tier | Status | Derived Path | Notes |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
    ))

    # knowledge/
    (root / "knowledge").mkdir()
    _write(root / "knowledge" / "note-alpha.md", _artifact("Alpha Note", description="About alpha."))
    _write(root / "knowledge" / "note-beta.md", _artifact("Beta Note", status="draft"))

    # projects/
    (root / "projects").mkdir()
    _write(root / "projects" / "milestone-x.md", _artifact("Milestone X", status="active"))

    # docs/ — index exempt from frontmatter requirement
    (root / "docs").mkdir()
    _write(root / "docs" / "guide.md", "# Guide\n\nSome guide text.\n")

    return root


class TestGenerateIndexes(unittest.TestCase):
    """Unit tests for generate() against a temp wiki."""

    def _gen(self, root: Path, **kwargs):
        from tools.generate_indexes import generate
        return generate(root, **kwargs)

    # ------------------------------------------------------------------
    # Core: index.md exists in each populated directory
    # ------------------------------------------------------------------

    def test_index_created_in_each_governed_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_wiki(Path(tmp))
            result = self._gen(root)

            # knowledge/ and projects/ should get an index.md
            self.assertTrue((root / "knowledge" / "index.md").exists())
            self.assertTrue((root / "projects" / "index.md").exists())
            # meta/index.md is always regenerated
            self.assertTrue((root / "meta" / "index.md").exists())
            # At least knowledge + projects + meta in written
            self.assertGreater(len(result.written), 0)

    # ------------------------------------------------------------------
    # Entries show title + status
    # ------------------------------------------------------------------

    def test_entries_contain_title_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_wiki(Path(tmp))
            self._gen(root)

            knowledge_index = (root / "knowledge" / "index.md").read_text(encoding="utf-8")
            self.assertIn("Alpha Note", knowledge_index)
            self.assertIn("Beta Note", knowledge_index)
            self.assertIn("[active]", knowledge_index)
            self.assertIn("[draft]", knowledge_index)

    # ------------------------------------------------------------------
    # Description is present when provided; absent otherwise
    # ------------------------------------------------------------------

    def test_description_shown_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_wiki(Path(tmp))
            self._gen(root)

            text = (root / "knowledge" / "index.md").read_text(encoding="utf-8")
            self.assertIn("About alpha.", text)

    def test_missing_description_degrades_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_wiki(Path(tmp))
            self._gen(root)

            text = (root / "knowledge" / "index.md").read_text(encoding="utf-8")
            # Beta Note has no description — entry should still be there, no placeholder
            self.assertIn("Beta Note", text)
            self.assertNotIn("placeholder", text.lower())
            # The description separator " — " should NOT appear for Beta Note's line
            beta_line = next(
                (ln for ln in text.splitlines() if "Beta Note" in ln),
                "",
            )
            self.assertNotIn(" — ", beta_line)

    # ------------------------------------------------------------------
    # Relative links to child directories
    # ------------------------------------------------------------------

    def test_child_dir_links_are_relative(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_wiki(Path(tmp))
            # Add a sub-directory inside knowledge/
            (root / "knowledge" / "sub").mkdir()
            _write(root / "knowledge" / "sub" / "note-sub.md", _artifact("Sub Note"))
            self._gen(root)

            knowledge_index = (root / "knowledge" / "index.md").read_text(encoding="utf-8")
            # Should link to sub/index.md (relative, not absolute)
            self.assertIn("sub/index.md", knowledge_index)
            self.assertNotIn(str(root), knowledge_index)

    # ------------------------------------------------------------------
    # Idempotence
    # ------------------------------------------------------------------

    def test_second_run_is_byte_identical_and_no_new_log_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_wiki(Path(tmp))

            first = self._gen(root)
            content_after_first = {
                str(p): p.read_text(encoding="utf-8")
                for p in root.rglob("index.md")
            }
            log_after_first = (root / "meta" / "log.md").read_text(encoding="utf-8") if (root / "meta" / "log.md").exists() else ""

            second = self._gen(root)

            # All written files should now be unchanged
            self.assertEqual(set(), second.written)
            self.assertFalse(second.log_appended)

            # Content unchanged
            for path_str, original_content in content_after_first.items():
                current = Path(path_str).read_text(encoding="utf-8")
                self.assertEqual(original_content, current, f"{path_str} changed on second run")

            # Log not appended again
            log_after_second = (root / "meta" / "log.md").read_text(encoding="utf-8") if (root / "meta" / "log.md").exists() else ""
            self.assertEqual(log_after_first, log_after_second)

    # ------------------------------------------------------------------
    # Log: append-on-change, no-op on no-change
    # ------------------------------------------------------------------

    def test_log_appended_on_first_run_with_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_wiki(Path(tmp))
            result = self._gen(root)

            self.assertTrue(result.log_appended)
            log_path = root / "meta" / "log.md"
            self.assertTrue(log_path.exists())
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("index", log_text.lower())

    def test_log_not_appended_on_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_wiki(Path(tmp))
            self._gen(root)  # first run writes
            result = self._gen(root)  # second run is no-op
            self.assertFalse(result.log_appended)

    def test_log_preserves_prior_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_wiki(Path(tmp))
            # Pre-populate log with an existing entry
            _write(root / "meta" / "log.md", (
                "---\nartifact_type: log\nstatus: active\nupdated: 2020-01-01\n---\n\n"
                "# Maintenance Log\n\n"
                "## 2020-01-01\n\n"
                "- Prior entry.\n\n"
            ))

            self._gen(root)

            log_text = (root / "meta" / "log.md").read_text(encoding="utf-8")
            self.assertIn("2020-01-01", log_text)
            self.assertIn("Prior entry.", log_text)

    # ------------------------------------------------------------------
    # dry_run writes nothing
    # ------------------------------------------------------------------

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_wiki(Path(tmp))
            result = self._gen(root, dry_run=True)

            self.assertTrue(result.dry_run)
            self.assertGreater(len(result.written), 0)  # non-empty change set
            self.assertFalse((root / "knowledge" / "index.md").exists())
            self.assertFalse((root / "projects" / "index.md").exists())

    # ------------------------------------------------------------------
    # Validator passes after generation
    # ------------------------------------------------------------------

    def test_validator_passes_after_generation(self):
        """The structural validator should emit no errors over the temp wiki."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _minimal_wiki(Path(tmp))
            self._gen(root)

            from tools.validate_repo import (
                markdown_files,
                registered_sources,
                validate_frontmatter,
                validate_links,
            )
            from unittest import mock

            # Patch ROOT inside validate_repo to point to our temp wiki
            import tools.validate_repo as vr
            with mock.patch.object(vr, "ROOT", root):
                sources = registered_sources(root)
                errors: list[str] = []
                validate_frontmatter(errors, sources)
                validate_links(errors)

            # Filter out errors from files we didn't generate (docs/guide.md
            # has no frontmatter — that's fine for docs/)
            relevant = [
                e for e in errors
                if "index.md" in e or "meta/" in e
            ]
            self.assertEqual([], relevant, f"Validator errors: {errors}")


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestIndexCommand(unittest.TestCase):
    """CliRunner tests for the ``index`` and ``reindex`` commands."""

    def setUp(self):
        from typer.testing import CliRunner
        from llm_wiki_wizard.cli import app

        self.runner = CliRunner()
        self.app = app

    def _temp_wiki_root(self) -> tempfile.TemporaryDirectory:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name) / "wiki"
        root.mkdir()
        (root / "knowledge").mkdir()
        _write(root / "knowledge" / "note.md", _artifact("CLI Note", description="For CLI test."))
        (root / "meta").mkdir()
        _write(root / "meta" / "source-registry.md", (
            "---\nartifact_type: source-registry\nstatus: active\n---\n\n"
            "# Source Registry\n\n"
            "| Source ID | Title | Tier | Status | Derived Path | Notes |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
        ))
        return td, root

    def test_index_command_generates_indexes(self):
        td, root = self._temp_wiki_root()
        try:
            result = self.runner.invoke(self.app, ["index", str(root)])
            self.assertEqual(0, result.exit_code, result.output)
            self.assertTrue((root / "knowledge" / "index.md").exists())
        finally:
            td.cleanup()

    def test_reindex_command_is_alias(self):
        td, root = self._temp_wiki_root()
        try:
            result = self.runner.invoke(self.app, ["reindex", str(root)])
            self.assertEqual(0, result.exit_code, result.output)
            self.assertTrue((root / "knowledge" / "index.md").exists())
        finally:
            td.cleanup()

    def test_dry_run_writes_nothing_reports_change_set(self):
        td, root = self._temp_wiki_root()
        try:
            result = self.runner.invoke(self.app, ["index", str(root), "--dry-run"])
            self.assertEqual(0, result.exit_code, result.output)
            self.assertFalse((root / "knowledge" / "index.md").exists())
            # Output should mention something was would be written
            self.assertIn("Would write", result.output)
        finally:
            td.cleanup()

    def test_json_output_emits_result_dict(self):
        td, root = self._temp_wiki_root()
        try:
            result = self.runner.invoke(self.app, ["index", str(root), "--json"])
            self.assertEqual(0, result.exit_code, result.output)
            payload = json.loads(result.output)
            self.assertIn("written", payload)
            self.assertIn("unchanged", payload)
            self.assertIn("log_appended", payload)
            self.assertIn("dry_run", payload)
        finally:
            td.cleanup()

    def test_json_dry_run_combination(self):
        td, root = self._temp_wiki_root()
        try:
            result = self.runner.invoke(self.app, ["index", str(root), "--dry-run", "--json"])
            self.assertEqual(0, result.exit_code, result.output)
            payload = json.loads(result.output)
            self.assertTrue(payload["dry_run"])
            self.assertGreater(len(payload["written"]), 0)
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
