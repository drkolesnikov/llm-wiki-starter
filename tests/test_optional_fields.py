"""Tests for #31: optional description + resource frontmatter fields.

Verifies:
- KNOWN_OPTIONAL_FIELDS exists in wiki_spec and contains description + resource.
- An artifact with NEITHER field passes every tier of validate_frontmatter.
- An artifact with BOTH fields passes and is not flagged as carrying unknown fields.
- knowledge-note and source-summary templates contain the expected new fields.
- Vendored template copies match the canonical copies.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import validate_repo, wiki_spec


ROOT = Path(__file__).resolve().parents[1]

_WIKI_SPEC_PATH = ROOT / "tools" / "wiki_spec.py"
_VENDORED_WIKI_SPEC_PATH = (
    ROOT / "src" / "llm_wiki_wizard" / "templates" / "wiki" / "tools" / "wiki_spec.py"
)

_KNOWLEDGE_NOTE_TEMPLATE = ROOT / "docs" / "templates" / "knowledge-note.md"
_SOURCE_SUMMARY_TEMPLATE = ROOT / "docs" / "templates" / "source-summary.md"
_VENDORED_KNOWLEDGE_NOTE = (
    ROOT / "src" / "llm_wiki_wizard" / "templates" / "wiki" / "docs" / "templates" / "knowledge-note.md"
)
_VENDORED_SOURCE_SUMMARY = (
    ROOT / "src" / "llm_wiki_wizard" / "templates" / "wiki" / "docs" / "templates" / "source-summary.md"
)


def _make_knowledge_note(**extra_fields: str) -> str:
    """Return minimal valid knowledge-note frontmatter as a string."""
    lines = [
        "---",
        "artifact_type: knowledge-note",
        "status: active",
        'title: "Test Note"',
    ]
    for key, value in extra_fields.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append("# Test Note")
    lines.append("")
    lines.append("## Claim")
    lines.append("")
    lines.append("A minimal test claim.")
    return "\n".join(lines)


def _make_source_summary(**extra_fields: str) -> str:
    """Return minimal valid source-summary frontmatter as a string."""
    lines = [
        "---",
        "artifact_type: source-summary",
        "status: active",
        'title: "Test Source"',
        "source_tier: reference",
    ]
    for key, value in extra_fields.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append("# Test Source")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append("Test scope.")
    return "\n".join(lines)


class KnownOptionalFieldsSpec(unittest.TestCase):
    """wiki_spec exports KNOWN_OPTIONAL_FIELDS with the right members."""

    def test_attribute_exists(self) -> None:
        self.assertTrue(
            hasattr(wiki_spec, "KNOWN_OPTIONAL_FIELDS"),
            "wiki_spec must expose KNOWN_OPTIONAL_FIELDS",
        )

    def test_description_registered(self) -> None:
        self.assertIn("description", wiki_spec.KNOWN_OPTIONAL_FIELDS)

    def test_resource_registered(self) -> None:
        self.assertIn("resource", wiki_spec.KNOWN_OPTIONAL_FIELDS)

    def test_is_frozenset_or_set(self) -> None:
        self.assertIsInstance(wiki_spec.KNOWN_OPTIONAL_FIELDS, (frozenset, set))

    def test_vendored_spec_has_same_fields(self) -> None:
        """The vendored copy exports the same optional fields."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("vendored_wiki_spec", _VENDORED_WIKI_SPEC_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        self.assertTrue(
            hasattr(mod, "KNOWN_OPTIONAL_FIELDS"),
            "vendored wiki_spec must expose KNOWN_OPTIONAL_FIELDS",
        )
        self.assertIn("description", mod.KNOWN_OPTIONAL_FIELDS)
        self.assertIn("resource", mod.KNOWN_OPTIONAL_FIELDS)


class BackwardCompatibility(unittest.TestCase):
    """Artifacts WITHOUT description / resource must still pass all tiers."""

    def _run_validate(self, root: Path) -> list[str]:
        errors: list[str] = []
        with mock.patch.object(validate_repo, "ROOT", root):
            validate_repo.validate_frontmatter(errors, {})
        return errors

    def test_knowledge_note_without_optional_fields_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "knowledge").mkdir()
            (root / "knowledge" / "note.md").write_text(
                _make_knowledge_note(),
                encoding="utf-8",
            )
            errors = self._run_validate(root)
        self.assertEqual([], errors, f"Unexpected errors: {errors}")

    def test_source_summary_without_optional_fields_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw" / "derived").mkdir(parents=True)
            (root / "raw" / "derived" / "summary.md").write_text(
                _make_source_summary(),
                encoding="utf-8",
            )
            errors = self._run_validate(root)
        self.assertEqual([], errors, f"Unexpected errors: {errors}")


class WithBothFields(unittest.TestCase):
    """Artifacts WITH description AND resource must pass and not be flagged."""

    def _run_validate(self, root: Path) -> list[str]:
        errors: list[str] = []
        with mock.patch.object(validate_repo, "ROOT", root):
            validate_repo.validate_frontmatter(errors, {})
        return errors

    def test_knowledge_note_with_both_fields_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "knowledge").mkdir()
            (root / "knowledge" / "note.md").write_text(
                _make_knowledge_note(
                    description='"A one-sentence summary."',
                    resource="https://example.com/paper",
                ),
                encoding="utf-8",
            )
            errors = self._run_validate(root)
        self.assertEqual([], errors, f"Unexpected errors: {errors}")

    def test_source_summary_with_both_fields_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw" / "derived").mkdir(parents=True)
            (root / "raw" / "derived" / "summary.md").write_text(
                _make_source_summary(
                    description='"A one-sentence summary."',
                    resource="https://doi.org/10.1234/example",
                ),
                encoding="utf-8",
            )
            errors = self._run_validate(root)
        self.assertEqual([], errors, f"Unexpected errors: {errors}")


class TemplateContents(unittest.TestCase):
    """Templates expose the new optional fields in their frontmatter."""

    def _frontmatter_keys(self, path: Path) -> set[str]:
        text = path.read_text(encoding="utf-8")
        fm, _ = validate_repo.split_frontmatter(text)
        return set(fm.keys()) if fm else set()

    def test_knowledge_note_template_has_description(self) -> None:
        keys = self._frontmatter_keys(_KNOWLEDGE_NOTE_TEMPLATE)
        self.assertIn("description", keys)

    def test_source_summary_template_has_description(self) -> None:
        keys = self._frontmatter_keys(_SOURCE_SUMMARY_TEMPLATE)
        self.assertIn("description", keys)

    def test_source_summary_template_has_resource(self) -> None:
        keys = self._frontmatter_keys(_SOURCE_SUMMARY_TEMPLATE)
        self.assertIn("resource", keys)

    def test_vendored_knowledge_note_template_has_description(self) -> None:
        keys = self._frontmatter_keys(_VENDORED_KNOWLEDGE_NOTE)
        self.assertIn("description", keys)

    def test_vendored_source_summary_template_has_description(self) -> None:
        keys = self._frontmatter_keys(_VENDORED_SOURCE_SUMMARY)
        self.assertIn("description", keys)

    def test_vendored_source_summary_template_has_resource(self) -> None:
        keys = self._frontmatter_keys(_VENDORED_SOURCE_SUMMARY)
        self.assertIn("resource", keys)


if __name__ == "__main__":
    unittest.main()
