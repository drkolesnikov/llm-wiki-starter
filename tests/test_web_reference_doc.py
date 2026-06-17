"""Tests for tools/source-ingest/web/emitter.py — issue #36.

Covers:
- reference decision registers source via registry (#32)
- reference decision emits a source-summary / reference-tier doc citing the source
- emitter refuses when registration fails (EmissionError raised, no file written)
- validate_repo passes for an emitted reference doc
"""

from __future__ import annotations

import importlib.util
import sys
import types
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EMITTER_PATH = ROOT / "tools" / "source-ingest" / "web" / "emitter.py"
ROUTER_PATH = ROOT / "tools" / "source-ingest" / "web" / "router.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"Cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


router_mod = _load_module("web_router_for_emitter_tests", ROUTER_PATH)
emitter_mod = _load_module("web_emitter", EMITTER_PATH)

emit_reference_doc = emitter_mod.emit_reference_doc
EmissionError = emitter_mod.EmissionError
EmissionResult = emitter_mod.EmissionResult


# ---------------------------------------------------------------------------
# Registry header for a minimal registry file
# ---------------------------------------------------------------------------

_REGISTRY_HEADER = (
    "---\n"
    "artifact_type: source-registry\n"
    "status: active\n"
    "owner: agents\n"
    "updated: 2026-01-01\n"
    "---\n"
    "\n"
    "# Source Registry\n"
    "\n"
    "Register sources before they support durable knowledge artifacts.\n"
    "\n"
    "| Source ID | Title | Tier | Status | Derived Path | Notes |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
)


def _make_decision(
    url: str = "https://example.com/docs/guide",
    title: str = "Example Guide",
    extract: str = "This is a guide about something useful. " * 10,
    outcome: str = "reference",
) -> types.SimpleNamespace:
    d = types.SimpleNamespace()
    d.outcome = outcome
    d.url = url
    d.page_title = title
    d.page_extract = extract
    d.rationale = "test decision"
    d.target_artifact_id = None
    return d


def _make_registry(tmp: Path) -> Path:
    path = tmp / "source-registry.md"
    path.write_text(_REGISTRY_HEADER, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests: emit_reference_doc happy path
# ---------------------------------------------------------------------------


class TestEmitReferencDocHappyPath(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.registry_path = _make_registry(self.tmp)
        self.output_dir = self.tmp / "raw" / "derived" / "web"

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_emission_result(self):
        d = _make_decision()
        result = emit_reference_doc(
            decision=d,
            registry_path=self.registry_path,
            output_dir=self.output_dir,
            today="2026-06-17",
        )
        self.assertIsInstance(result, EmissionResult)

    def test_artifact_file_is_written(self):
        d = _make_decision()
        result = emit_reference_doc(
            decision=d,
            registry_path=self.registry_path,
            output_dir=self.output_dir,
            today="2026-06-17",
        )
        self.assertTrue(result.artifact_path.exists(),
                        f"Expected file at {result.artifact_path}")

    def test_artifact_has_source_summary_type(self):
        d = _make_decision()
        result = emit_reference_doc(
            decision=d,
            registry_path=self.registry_path,
            output_dir=self.output_dir,
            today="2026-06-17",
        )
        self.assertIn("artifact_type: source-summary", result.content)

    def test_artifact_has_reference_tier(self):
        d = _make_decision()
        result = emit_reference_doc(
            decision=d,
            registry_path=self.registry_path,
            output_dir=self.output_dir,
            today="2026-06-17",
        )
        self.assertIn("source_tier: reference", result.content)

    def test_artifact_cites_registered_source_id(self):
        d = _make_decision()
        result = emit_reference_doc(
            decision=d,
            registry_path=self.registry_path,
            output_dir=self.output_dir,
            today="2026-06-17",
        )
        # The source_id field must appear in the frontmatter.
        self.assertIn(f"source_id: {result.source_id}", result.content)
        # And the sources list must reference it.
        self.assertIn(f"  - {result.source_id}", result.content)

    def test_source_is_registered_in_registry(self):
        d = _make_decision()
        result = emit_reference_doc(
            decision=d,
            registry_path=self.registry_path,
            output_dir=self.output_dir,
            today="2026-06-17",
        )
        registry_text = self.registry_path.read_text(encoding="utf-8")
        self.assertIn(result.source_id, registry_text)

    def test_source_tier_is_reference_in_registry(self):
        d = _make_decision()
        result = emit_reference_doc(
            decision=d,
            registry_path=self.registry_path,
            output_dir=self.output_dir,
            today="2026-06-17",
        )
        registry_text = self.registry_path.read_text(encoding="utf-8")
        # The row must record tier=reference.
        self.assertIn("reference", registry_text)

    def test_artifact_contains_url(self):
        url = "https://example.com/docs/guide"
        d = _make_decision(url=url)
        result = emit_reference_doc(
            decision=d,
            registry_path=self.registry_path,
            output_dir=self.output_dir,
            today="2026-06-17",
        )
        self.assertIn(url, result.content)

    def test_artifact_contains_extract(self):
        extract = "This is a guide about something useful. " * 10
        d = _make_decision(extract=extract)
        result = emit_reference_doc(
            decision=d,
            registry_path=self.registry_path,
            output_dir=self.output_dir,
            today="2026-06-17",
        )
        # At least the first few words of the extract should appear.
        self.assertIn("This is a guide", result.content)

    def test_output_dir_created_if_absent(self):
        missing_dir = self.tmp / "brand" / "new" / "dir"
        self.assertFalse(missing_dir.exists())
        d = _make_decision()
        emit_reference_doc(
            decision=d,
            registry_path=self.registry_path,
            output_dir=missing_dir,
            today="2026-06-17",
        )
        self.assertTrue(missing_dir.exists())

    def test_result_source_id_matches_registry_entry(self):
        d = _make_decision()
        result = emit_reference_doc(
            decision=d,
            registry_path=self.registry_path,
            output_dir=self.output_dir,
            today="2026-06-17",
        )
        registry_text = self.registry_path.read_text(encoding="utf-8")
        self.assertIn(result.source_id, registry_text)


# ---------------------------------------------------------------------------
# Tests: emitter refuses on wrong outcome
# ---------------------------------------------------------------------------


class TestEmitterRefusesWrongOutcome(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.registry_path = _make_registry(self.tmp)
        self.output_dir = self.tmp / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def test_raises_value_error_for_enrich_outcome(self):
        d = _make_decision(outcome="enrich")
        d.target_artifact_id = "some-artifact"
        with self.assertRaises(ValueError):
            emit_reference_doc(
                decision=d,
                registry_path=self.registry_path,
                output_dir=self.output_dir,
            )

    def test_raises_value_error_for_skip_outcome(self):
        d = _make_decision(outcome="skip")
        with self.assertRaises(ValueError):
            emit_reference_doc(
                decision=d,
                registry_path=self.registry_path,
                output_dir=self.output_dir,
            )


# ---------------------------------------------------------------------------
# Tests: emitter refuses when registration fails
# ---------------------------------------------------------------------------


class TestEmitterRefusesOnRegistrationFailure(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.registry_path = _make_registry(self.tmp)
        self.output_dir = self.tmp / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def test_raises_emission_error_when_no_url(self):
        d = _make_decision()
        d.url = ""  # strip URL → registration will fail (locator required)
        with self.assertRaises(EmissionError):
            emit_reference_doc(
                decision=d,
                registry_path=self.registry_path,
                output_dir=self.output_dir,
            )

    def test_no_file_written_when_registration_fails(self):
        d = _make_decision()
        d.url = ""
        try:
            emit_reference_doc(
                decision=d,
                registry_path=self.registry_path,
                output_dir=self.output_dir,
            )
        except (EmissionError, Exception):
            pass
        # No Markdown file should have been written.
        md_files = list(self.output_dir.rglob("*.md")) if self.output_dir.exists() else []
        self.assertEqual([], md_files,
                         "No file should be written when registration fails")


# ---------------------------------------------------------------------------
# Tests: validate_repo passes for an emitted reference doc
# ---------------------------------------------------------------------------


class TestValidateRepoPassesForEmittedDoc(unittest.TestCase):
    """Smoke-test that validate_repo.py structural check accepts emitted docs."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_emitted_doc_passes_structural_checks(self):
        import importlib
        # Build a minimal wiki tree under tmp/.
        meta_dir = self.tmp / "meta"
        meta_dir.mkdir(parents=True)
        registry_path = meta_dir / "source-registry.md"
        registry_path.write_text(_REGISTRY_HEADER, encoding="utf-8")

        output_dir = self.tmp / "raw" / "derived" / "web"

        d = _make_decision(
            url="https://example.com/ai/overview",
            title="AI Overview",
            extract="Artificial intelligence overview content. " * 20,
        )
        result = emit_reference_doc(
            decision=d,
            registry_path=registry_path,
            output_dir=output_dir,
            today="2026-06-17",
        )

        # Load validate_repo and point ROOT at our tmp directory.
        vr_path = ROOT / "tools" / "validate_repo.py"
        spec = importlib.util.spec_from_file_location("validate_repo_test", vr_path)
        assert spec and spec.loader
        vr = importlib.util.module_from_spec(spec)
        sys.modules["validate_repo_test"] = vr
        spec.loader.exec_module(vr)

        # Collect only frontmatter + registry errors for the emitted file.
        sources = vr.registered_sources(self.tmp)
        # The emitted source must be present in the registry.
        self.assertIn(result.source_id, sources,
                      f"Source {result.source_id!r} not found in registry")

        # Check that the emitted doc's frontmatter is structurally valid.
        artifact_text = result.artifact_path.read_text(encoding="utf-8")
        frontmatter, _ = vr.split_frontmatter(artifact_text)
        self.assertIsNotNone(frontmatter, "Emitted doc must have frontmatter")
        self.assertEqual("source-summary", frontmatter.get("artifact_type"))
        self.assertEqual("reference", frontmatter.get("source_tier"))
        self.assertIn("needs-review", frontmatter.get("status", ""))

        # Check that the source cited in the doc's frontmatter is registered.
        errors: list[str] = []
        cited = vr.source_values(frontmatter)
        for sid in cited:
            if sid not in sources:
                errors.append(f"source {sid!r} not registered")
        self.assertEqual([], errors, f"Source citation errors: {errors}")


if __name__ == "__main__":
    unittest.main()
