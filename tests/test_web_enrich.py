"""Tests for tools/source-ingest/web/enrich.py — issue #50.

Covers:
- STUB provider → needs-review draft with expected sections (## Summary,
  ## Key Facts, ## Source Structure, ## Source References, ## Related Concepts)
- Disabled provider → no artifact written + reason "enrichment disabled"
- CliRunner: ``llm-wiki enrich`` reports "enrichment disabled" when no provider
  is configured (default DisabledProvider).
- CliRunner: ``llm-wiki enrich`` auto-discovered (appears in --help).
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Ensure the repo root is on sys.path so ``tools`` and the installed package
# are both importable.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_ENRICH_PATH = _REPO_ROOT / "tools" / "source-ingest" / "web" / "enrich.py"


def _load_enrich():
    spec = importlib.util.spec_from_file_location("_test_web_enrich", _ENRICH_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


enrich_mod = _load_enrich()
enrich_source = enrich_mod.enrich_source
EnrichResult = enrich_mod.EnrichResult


# ---------------------------------------------------------------------------
# Stub provider that is enabled and returns canned LLM output.
# ---------------------------------------------------------------------------

_STUB_BODY = (
    "## Summary\n"
    "A brief summary of the source.\n\n"
    "## Key Facts\n"
    "- Fact one\n"
    "- Fact two\n\n"
    "## Source Structure\n"
    "The source is structured as a multi-page guide.\n\n"
    "## Source References\n"
    "- Reference A\n\n"
    "## Related Concepts\n"
    "- Concept X\n"
    "- Concept Y\n"
)


class _StubProvider:
    enabled = True

    def complete(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        return _STUB_BODY


class _DisabledProvider:
    enabled = False

    def complete(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        raise RuntimeError("Should never be called on a disabled provider")


# ---------------------------------------------------------------------------
# Tests: enrich_source() function
# ---------------------------------------------------------------------------

class TestEnrichSourceWithStubProvider(unittest.TestCase):
    """Stub provider → writes a needs-review draft with the expected sections."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._output_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, **kwargs):
        defaults = dict(
            source_id="example-docs-guide",
            title="Example Guide",
            url="https://example.com/docs/guide",
            extract="This is a guide about something useful.",
            output_dir=self._output_dir,
            provider=_StubProvider(),
        )
        defaults.update(kwargs)
        return enrich_source(**defaults)

    def test_result_not_skipped(self):
        result = self._run()
        self.assertFalse(result.skipped)

    def test_artifact_path_exists(self):
        result = self._run()
        self.assertIsNotNone(result.artifact_path)
        self.assertTrue(result.artifact_path.exists())

    def test_source_id_returned(self):
        result = self._run()
        self.assertEqual("example-docs-guide", result.source_id)

    def test_frontmatter_status_needs_review(self):
        result = self._run()
        self.assertIn("status: needs-review", result.content)

    def test_frontmatter_artifact_type_default(self):
        result = self._run()
        self.assertIn("artifact_type: source-summary", result.content)

    def test_frontmatter_artifact_type_knowledge_note(self):
        result = self._run(artifact_type="knowledge-note")
        self.assertIn("artifact_type: knowledge-note", result.content)

    def test_frontmatter_source_id(self):
        result = self._run()
        self.assertIn("source_id: example-docs-guide", result.content)

    def test_frontmatter_resource_url(self):
        result = self._run()
        self.assertIn("resource: https://example.com/docs/guide", result.content)

    def test_section_summary(self):
        result = self._run()
        self.assertIn("## Summary", result.content)

    def test_section_key_facts(self):
        result = self._run()
        self.assertIn("## Key Facts", result.content)

    def test_section_source_structure(self):
        result = self._run()
        self.assertIn("## Source Structure", result.content)

    def test_section_source_references(self):
        result = self._run()
        self.assertIn("## Source References", result.content)

    def test_section_related_concepts(self):
        result = self._run()
        self.assertIn("## Related Concepts", result.content)

    def test_stub_body_in_content(self):
        result = self._run()
        self.assertIn("A brief summary of the source.", result.content)

    def test_title_in_content(self):
        result = self._run()
        self.assertIn("Example Guide", result.content)

    def test_artifact_file_on_disk_matches_content(self):
        result = self._run()
        on_disk = result.artifact_path.read_text(encoding="utf-8")
        self.assertEqual(result.content, on_disk)

    def test_file_written_into_output_dir(self):
        result = self._run()
        self.assertEqual(self._output_dir, result.artifact_path.parent)

    def test_output_dir_created_if_missing(self):
        nested = self._output_dir / "a" / "b" / "c"
        result = self._run(output_dir=nested)
        self.assertTrue(result.artifact_path.exists())


class TestEnrichSourceDisabledProvider(unittest.TestCase):
    """Disabled provider → no artifact, reason == 'enrichment disabled'."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._output_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, **kwargs):
        defaults = dict(
            source_id="some-source",
            title="Some Source",
            url="https://example.com/some",
            output_dir=self._output_dir,
            provider=_DisabledProvider(),
        )
        defaults.update(kwargs)
        return enrich_source(**defaults)

    def test_skipped_is_true(self):
        result = self._run()
        self.assertTrue(result.skipped)

    def test_reason_is_enrichment_disabled(self):
        result = self._run()
        self.assertIn("disabled", result.reason)

    def test_no_artifact_path(self):
        result = self._run()
        self.assertIsNone(result.artifact_path)

    def test_no_content(self):
        result = self._run()
        self.assertIsNone(result.content)

    def test_no_files_written(self):
        self._run()
        files = list(self._output_dir.rglob("*"))
        self.assertEqual([], files, "No files should be written when provider is disabled")

    def test_default_provider_is_disabled(self):
        """get_provider() returns DisabledProvider by default → skipped."""
        result = enrich_source(
            source_id="x",
            title="X",
            url="https://x.example.com/",
            output_dir=self._output_dir,
        )
        self.assertTrue(result.skipped)
        self.assertIn("disabled", result.reason)


# ---------------------------------------------------------------------------
# Tests: CLI via CliRunner
# ---------------------------------------------------------------------------

from typer.testing import CliRunner  # noqa: E402
from llm_wiki_wizard.cli import app  # noqa: E402


class TestEnrichCommandAutodiscovery(unittest.TestCase):
    def test_enrich_appears_in_help(self):
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn("enrich", result.output)

    def test_enrich_command_exists_in_registered(self):
        names = {info.name or info.callback.__name__ for info in app.registered_commands}
        self.assertIn("enrich", names)


class TestEnrichCommandDisabledProvider(unittest.TestCase):
    """CliRunner: enrich reports 'enrichment disabled' with the default provider."""

    def _invoke(self, extra_args=None):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            args = [
                "enrich",
                "my-source-id",
                "--title", "My Source",
                "--url", "https://example.com/source",
                "--output-dir", tmp,
            ]
            if extra_args:
                args.extend(extra_args)
            return runner.invoke(app, args)

    def test_exit_code_zero_when_disabled(self):
        result = self._invoke()
        self.assertEqual(0, result.exit_code, result.output)

    def test_reports_enrichment_disabled(self):
        result = self._invoke()
        self.assertIn("disabled", result.output.lower())

    def test_no_file_written_when_disabled(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            runner.invoke(app, [
                "enrich", "my-source-id",
                "--title", "My Source",
                "--url", "https://example.com/source",
                "--output-dir", tmp,
            ])
            files = list(Path(tmp).rglob("*"))
            self.assertEqual([], files)


if __name__ == "__main__":
    unittest.main()
