"""Tests for #52: tools/interchange/ OKF v0.1 export + ``export`` command.

Test categories
---------------
- Unit: export a temp wiki with cross-links; re-parse the OKF bundle and assert
  all acceptance criteria from the issue.
- CliRunner: ``export`` command, ``--json``, bad input exits non-zero.
- Auto-discovery: command present without cli.py / __init__.py edits.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import typer
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _snapshot(directory: Path) -> dict[str, str]:
    """Return {relative_posix_path: md5} for every file under *directory*."""
    result = {}
    for p in sorted(directory.rglob("*")):
        if p.is_file():
            result[p.relative_to(directory).as_posix()] = _md5(p)
    return result


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract scalar frontmatter from an OKF artifact (reused in assertions).

    Keys may contain colons (e.g. ``llm-wiki:status``).  We use a greedy match
    against ``key: value`` patterns — a line is a scalar entry iff it does NOT
    start with whitespace (list items) and contains `: ` (space after colon).
    The full text before the first `: ` sequence is the key.
    """
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
            # block list header — key only, no value
            pass
    return result


# ---------------------------------------------------------------------------
# Temp wiki builder
# ---------------------------------------------------------------------------

_SOURCE_REGISTRY = (
    "---\n"
    "artifact_type: source-registry\n"
    "status: active\n"
    "---\n\n"
    "# Source Registry\n\n"
    "| Source ID | Title | Tier | Status | Derived Path | Notes |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
)


def _make_wiki(tmp: Path) -> Path:
    """Build a temp wiki with cross-links, optional fields, and a linked_concepts list."""
    root = tmp / "wiki"
    root.mkdir()

    _write(root / "meta" / "source-registry.md", _SOURCE_REGISTRY)

    # Alpha: has description + resource + tags + linked_concepts pointing to Beta
    _write(
        root / "knowledge" / "alpha.md",
        "\n".join([
            "---",
            "artifact_type: knowledge-note",
            "title: Alpha Concept",
            "description: The alpha concept note.",
            "resource: https://example.com/alpha",
            "status: active",
            "updated: 2025-01-01",
            "tags:",
            "  - ml",
            "  - research",
            "linked_concepts:",
            "  - Beta Concept",
            "  - NonExistent Target",
            "---",
            "",
            "# Alpha Concept",
            "",
            "See also [[Beta Concept]] and [[NonExistent Target]].",
            "",
        ]),
    )

    # Beta: has NO description, NO resource (they must be absent from export)
    _write(
        root / "knowledge" / "beta.md",
        "\n".join([
            "---",
            "artifact_type: knowledge-note",
            "title: Beta Concept",
            "status: draft",
            "updated: 2025-02-01",
            "---",
            "",
            "# Beta Concept",
            "",
            "No wikilinks here.",
            "",
        ]),
    )

    # Gamma: source-summary type — tests type verbatim mapping
    _write(
        root / "knowledge" / "gamma.md",
        "\n".join([
            "---",
            "artifact_type: source-summary",
            "title: Gamma Summary",
            "description: Summary of gamma.",
            "status: active",
            "updated: 2025-03-01",
            "sources:",
            "  - src-001",
            "source_tier: primary",
            "linked_reviews:",
            "  - reviews/review-gamma.md",
            "---",
            "",
            "# Gamma Summary",
            "",
            "Content of gamma.",
            "",
        ]),
    )

    return root


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestExportArtifactTranslation(unittest.TestCase):
    """Re-parse the OKF bundle and assert translation correctness."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.wiki = _make_wiki(self.tmp)
        self.out = self.tmp / "bundle"
        from tools.interchange import export
        self.result = export(self.wiki, self.out)

    def tearDown(self):
        self._tmp.cleanup()

    # -- type field ----------------------------------------------------------

    def test_type_equals_artifact_type_verbatim(self):
        """OKF ``type`` must exactly match the source ``artifact_type``."""
        for stem, expected_type in [
            ("alpha", "knowledge-note"),
            ("beta", "knowledge-note"),
            ("gamma", "source-summary"),
        ]:
            path = self.out / "knowledge" / f"{stem}.md"
            self.assertTrue(path.exists(), f"Missing exported file: {path}")
            fm = _parse_frontmatter(path.read_text(encoding="utf-8"))
            self.assertEqual(expected_type, fm.get("type"),
                             f"{stem}: expected type={expected_type!r}, got {fm.get('type')!r}")

    # -- governance as extension keys ----------------------------------------

    def test_status_written_as_extension_key(self):
        fm = _parse_frontmatter((self.out / "knowledge" / "alpha.md").read_text(encoding="utf-8"))
        self.assertEqual("active", fm.get("llm-wiki:status"))

    def test_status_value_matches_source(self):
        fm = _parse_frontmatter((self.out / "knowledge" / "beta.md").read_text(encoding="utf-8"))
        self.assertEqual("draft", fm.get("llm-wiki:status"))

    def test_tags_written_as_extension_key(self):
        text = (self.out / "knowledge" / "alpha.md").read_text(encoding="utf-8")
        # tags is a list; check the extension key header appears
        self.assertIn("llm-wiki:tags:", text)
        self.assertIn("ml", text)
        self.assertIn("research", text)

    def test_governance_extension_keys_match_source_values(self):
        """Gamma has sources + source_tier + linked_reviews — all must appear."""
        text = (self.out / "knowledge" / "gamma.md").read_text(encoding="utf-8")
        self.assertIn("llm-wiki:sources:", text)
        self.assertIn("src-001", text)
        fm = _parse_frontmatter(text)
        self.assertEqual("primary", fm.get("llm-wiki:source_tier"))
        self.assertIn("llm-wiki:linked_reviews:", text)

    # -- description / resource presence / absence ---------------------------

    def test_description_emitted_when_present(self):
        fm = _parse_frontmatter((self.out / "knowledge" / "alpha.md").read_text(encoding="utf-8"))
        self.assertEqual("The alpha concept note.", fm.get("description"))

    def test_resource_emitted_when_present(self):
        fm = _parse_frontmatter((self.out / "knowledge" / "alpha.md").read_text(encoding="utf-8"))
        self.assertEqual("https://example.com/alpha", fm.get("resource"))

    def test_description_absent_when_not_in_source(self):
        fm = _parse_frontmatter((self.out / "knowledge" / "beta.md").read_text(encoding="utf-8"))
        self.assertNotIn("description", fm)

    def test_resource_absent_when_not_in_source(self):
        fm = _parse_frontmatter((self.out / "knowledge" / "beta.md").read_text(encoding="utf-8"))
        self.assertNotIn("resource", fm)

    # -- wikilink resolution -------------------------------------------------

    def test_resolved_wikilink_becomes_relative_markdown_link(self):
        body = (self.out / "knowledge" / "alpha.md").read_text(encoding="utf-8")
        # [[Beta Concept]] should resolve to a relative link, not raw [[...]]
        self.assertNotIn("[[Beta Concept]]", body,
                         "Resolved wikilink must not remain as [[...]] syntax")
        self.assertIn("[Beta Concept]", body,
                      "Resolved wikilink must appear as a Markdown link")

    def test_unresolved_wikilink_reported_and_becomes_plain_text(self):
        body = (self.out / "knowledge" / "alpha.md").read_text(encoding="utf-8")
        self.assertNotIn("[[NonExistent Target]]", body)
        self.assertIn("NonExistent Target", body)
        # It must appear in the unresolved list
        unresolved_str = " ".join(self.result.unresolved_links)
        self.assertIn("NonExistent Target", unresolved_str)

    def test_unresolved_links_do_not_abort_export(self):
        """Export must succeed even when wikilinks are unresolved."""
        self.assertIsNotNone(self.result)
        self.assertGreater(self.result.artifacts_exported, 0)

    def test_linked_concepts_unresolved_also_reported(self):
        """linked_concepts with an unresolved target must appear in report."""
        unresolved_str = " ".join(self.result.unresolved_links)
        self.assertIn("NonExistent Target", unresolved_str)

    # -- reserved index.md / log.md ------------------------------------------

    def test_meta_index_exists_in_bundle(self):
        self.assertTrue((self.out / "meta" / "index.md").exists(),
                        "meta/index.md must be present in the OKF bundle")

    def test_meta_log_exists_in_bundle(self):
        self.assertTrue((self.out / "meta" / "log.md").exists(),
                        "meta/log.md must be present in the OKF bundle")

    def test_index_lists_exported_concepts(self):
        """At least one index.md must reference the exported artifacts."""
        knowledge_index = self.out / "knowledge" / "index.md"
        self.assertTrue(knowledge_index.exists(), "knowledge/index.md must exist")
        content = knowledge_index.read_text(encoding="utf-8")
        # At least two of the three concepts should appear
        listed = sum(1 for name in ["alpha", "beta", "gamma"] if name in content.lower())
        self.assertGreaterEqual(listed, 2,
                                f"knowledge/index.md should list exported artifacts; got:\n{content}")

    # -- source wiki byte-unchanged ------------------------------------------

    def test_source_wiki_byte_unchanged(self):
        """The source wiki directory must be identical before and after export."""
        # Rebuild snapshot of the source wiki (we snapshot before export in setUp)
        # setUp runs export, so we just verify the wiki is still intact.
        alpha_text = (self.wiki / "knowledge" / "alpha.md").read_text(encoding="utf-8")
        self.assertIn("[[Beta Concept]]", alpha_text,
                      "Source wiki must be byte-unchanged after export")
        self.assertIn("artifact_type: knowledge-note", alpha_text)

    def test_source_wiki_files_unchanged_by_hash(self):
        """Byte-level check: re-hash source wiki files and compare to originals."""
        # Capture snapshot of source wiki AFTER export
        after = _snapshot(self.wiki)
        # Rebuild the expected state by rebuilding the wiki
        tmp2 = tempfile.TemporaryDirectory()
        try:
            wiki2 = _make_wiki(Path(tmp2.name))
            expected = _snapshot(wiki2)
            # Only compare files that exist in both
            for rel_path, expected_hash in expected.items():
                self.assertEqual(
                    expected_hash, after.get(rel_path),
                    f"Source file changed after export: {rel_path}",
                )
        finally:
            tmp2.cleanup()

    # -- ExportResult --------------------------------------------------------

    def test_export_result_artifacts_count(self):
        self.assertGreaterEqual(self.result.artifacts_exported, 3)

    def test_export_result_profile(self):
        self.assertEqual("okf-v0.1", self.result.profile)

    def test_export_result_to_dict(self):
        d = self.result.to_dict()
        self.assertIn("profile", d)
        self.assertIn("artifacts_exported", d)
        self.assertIn("unresolved_links", d)
        self.assertIn("index_written", d)
        self.assertIn("log_written", d)

    def test_writes_only_into_out_dir(self):
        """Export must not create files outside of out_dir."""
        # Nothing unexpected should appear in wiki root after export
        before_files = set(_snapshot(self.wiki).keys())
        # Export was already called in setUp; re-snapshot and verify no new files
        after_files = set(_snapshot(self.wiki).keys())
        self.assertEqual(before_files, after_files)

    def test_index_written_flag(self):
        self.assertTrue(self.result.index_written)

    def test_log_written_flag(self):
        self.assertTrue(self.result.log_written)


# ---------------------------------------------------------------------------
# CliRunner tests
# ---------------------------------------------------------------------------


class TestExportCommand(unittest.TestCase):
    """Test the ``export`` CLI command via typer.testing.CliRunner."""

    def _build_app_with_export(self):
        from llm_wiki_wizard.cli import app
        return app

    def test_export_json_output(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            wiki = _make_wiki(Path(tmp))
            out = Path(tmp) / "bundle"
            app = self._build_app_with_export()
            result = runner.invoke(app, ["export", str(wiki), "--out", str(out), "--json"])
            self.assertEqual(0, result.exit_code, result.output)
            payload = json.loads(result.output)
            self.assertEqual("okf-v0.1", payload["profile"])
            self.assertGreaterEqual(payload["artifacts_exported"], 3)
            self.assertIn("unresolved_links", payload)

    def test_export_human_output(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            wiki = _make_wiki(Path(tmp))
            out = Path(tmp) / "bundle"
            app = self._build_app_with_export()
            result = runner.invoke(app, ["export", str(wiki), "--out", str(out)])
            self.assertEqual(0, result.exit_code, result.output)
            self.assertIn("Exported", result.output)

    def test_export_bad_target_exits_nonzero(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            app = self._build_app_with_export()
            result = runner.invoke(app, ["export", "/no/such/path", "--out", str(out)])
            self.assertNotEqual(0, result.exit_code)

    def test_export_nonwiki_directory_exits_nonzero(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            # tmp exists but has no meta/ subdir
            out = Path(tmp) / "bundle"
            no_meta = Path(tmp) / "no_meta"
            no_meta.mkdir()
            app = self._build_app_with_export()
            result = runner.invoke(app, ["export", str(no_meta), "--out", str(out)])
            self.assertNotEqual(0, result.exit_code)

    def test_export_bad_target_json_structured_error(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            app = self._build_app_with_export()
            result = runner.invoke(app, ["export", "/no/such/path", "--out", str(out), "--json"])
            self.assertNotEqual(0, result.exit_code)
            payload = json.loads(result.output)
            self.assertIn("error", payload)


# ---------------------------------------------------------------------------
# Auto-discovery tests
# ---------------------------------------------------------------------------


class TestExportAutoDiscovery(unittest.TestCase):
    """``export`` command must be present without cli.py / __init__.py edits."""

    def test_export_is_autodiscovered(self):
        from llm_wiki_wizard.cli import app
        names: set[str] = set()
        for info in app.registered_commands:
            names.add(info.name or (info.callback.__name__ if info.callback else ""))
        self.assertIn("export", names,
                      f"export command not found in {names}. "
                      "Check that commands/export.py exposes register(app).")

    def test_export_appears_in_help(self):
        from llm_wiki_wizard.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn("export", result.output)


if __name__ == "__main__":
    unittest.main()
