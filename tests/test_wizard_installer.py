import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from llm_wiki_wizard.cli import app
from llm_wiki_wizard.installer import (
    POINTER_END,
    POINTER_START,
    SCAFFOLD_VERSION,
    initialize,
    rendered_template,
    status,
)


ROOT = Path(__file__).resolve().parents[1]


class WizardInstallerTests(unittest.TestCase):
    def test_clean_template_excludes_sample_artifacts(self):
        with rendered_template() as rendered:
            self.assertTrue((rendered / "AGENTS.md").exists())
            self.assertTrue((rendered / "tools" / "source-ingest" / "pdf" / "ingest_pdf.py").exists())
            self.assertFalse((rendered / "knowledge" / "llm-wiki-pattern.md").exists())
            self.assertFalse((rendered / "knowledge" / "karpathy-llm-wiki-pattern-summary.md").exists())
            self.assertFalse((rendered / "projects" / "decisions" / "adopt-docling-pdf-ingest.md").exists())
            self.assertFalse((rendered / "projects" / "milestones" / "wiki-foundation.md").exists())
            self.assertNotIn(
                "Karpathy",
                (rendered / "meta" / "source-registry.md").read_text(encoding="utf-8"),
            )

    def test_init_empty_repo_creates_namespaced_wiki_and_root_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            result = initialize(target)

            self.assertTrue((target / ".llm-wiki" / "AGENTS.md").exists())
            self.assertTrue((target / ".llm-wiki" / "docs").is_dir())
            self.assertTrue((target / ".llm-wiki" / "meta" / "install.json").exists())
            self.assertIn(".llm-wiki/AGENTS.md", (target / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertEqual([], result.conflicts)

            manifest = json.loads((target / ".llm-wiki" / "meta" / "install.json").read_text(encoding="utf-8"))
            self.assertEqual(SCAFFOLD_VERSION, manifest["template_version"])
            self.assertEqual(".llm-wiki", manifest["layout"])
            self.assertIn("AGENTS.md", manifest["managed_files"])

            current = status(target)
            self.assertTrue(current.wiki_exists)
            self.assertTrue(current.root_pointer_exists)
            self.assertEqual(SCAFFOLD_VERSION, current.scaffold_version)
            self.assertEqual([], current.missing_managed_files)
            self.assertEqual([], current.changed_managed_files)
            self.assertEqual([], current.unresolved_conflict_reports)

    def test_init_preserves_existing_root_agents_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / "AGENTS.md").write_text("# Host Agents\n\nHost rules stay.\n", encoding="utf-8")

            first = initialize(target)
            second = initialize(target)
            text = (target / "AGENTS.md").read_text(encoding="utf-8")

            self.assertEqual("appended", first.pointer_action)
            self.assertEqual("present", second.pointer_action)
            self.assertIn("Host rules stay.", text)
            self.assertEqual(1, text.count(POINTER_START))
            self.assertEqual(1, text.count(POINTER_END))
            self.assertEqual([], second.conflicts)

    def test_safe_merge_preserves_existing_wiki_file_and_reports_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            existing = target / ".llm-wiki" / "AGENTS.md"
            existing.parent.mkdir(parents=True)
            existing.write_text("keep my local wiki rules\n", encoding="utf-8")

            result = initialize(target)

            self.assertIn("AGENTS.md", result.conflicts)
            self.assertEqual("keep my local wiki rules\n", existing.read_text(encoding="utf-8"))
            report = (target / ".llm-wiki" / "meta" / "install-report.md").read_text(encoding="utf-8")
            self.assertIn("`AGENTS.md`", report)

            current = status(target)
            self.assertIn("AGENTS.md", current.changed_managed_files)
            self.assertEqual(
                [(target / ".llm-wiki" / "meta" / "install-report.md").resolve().as_posix()],
                current.unresolved_conflict_reports,
            )

    def test_status_detects_missing_and_changed_managed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            initialize(target)
            (target / ".llm-wiki" / "README.md").unlink()
            (target / ".llm-wiki" / "AGENTS.md").write_text("changed\n", encoding="utf-8")

            current = status(target)

            self.assertIn("README.md", current.missing_managed_files)
            self.assertIn("AGENTS.md", current.changed_managed_files)

    def test_dry_run_does_not_write_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            result = initialize(target, dry_run=True)

            self.assertTrue(result.dry_run)
            self.assertGreater(len(result.created_files), 0)
            self.assertFalse((target / ".llm-wiki").exists())
            self.assertFalse((target / "AGENTS.md").exists())

    def test_status_json_cli_fields(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            initialize(target)

            result = runner.invoke(app, ["status", str(target), "--json"])

            self.assertEqual(0, result.exit_code, result.output)
            payload = json.loads(result.output)
            self.assertTrue(payload["wiki_exists"])
            self.assertTrue(payload["root_pointer_exists"])
            self.assertEqual(SCAFFOLD_VERSION, payload["scaffold_version"])
            self.assertEqual([], payload["missing_managed_files"])

    def test_generated_wiki_validator_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            initialize(target)
            wiki_dir = target / ".llm-wiki"

            result = subprocess.run(
                [sys.executable, str(wiki_dir / "tools" / "validate_repo.py")],
                cwd=wiki_dir,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("Repository validation passed.", result.stdout)


class PluginScaffoldTests(unittest.TestCase):
    def test_plugin_manifest_shape(self):
        manifest = json.loads(
            (ROOT / "plugins" / "llm-wiki" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )

        self.assertEqual("llm-wiki", manifest["name"])
        self.assertEqual("0.1.0", manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertEqual("LLM Wiki", manifest["interface"]["displayName"])
        self.assertIn("Write", manifest["interface"]["capabilities"])

    def test_marketplace_entry_points_to_local_plugin(self):
        marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        plugins = {entry["name"]: entry for entry in marketplace["plugins"]}

        self.assertIn("llm-wiki", plugins)
        self.assertEqual("./plugins/llm-wiki", plugins["llm-wiki"]["source"]["path"])
        self.assertEqual("AVAILABLE", plugins["llm-wiki"]["policy"]["installation"])


if __name__ == "__main__":
    unittest.main()
