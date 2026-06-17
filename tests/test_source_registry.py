"""Tests for tools/source-ingest/registry.py."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "tools" / "source-ingest" / "registry.py"


def _load_registry_module():
    spec = importlib.util.spec_from_file_location("registry", REGISTRY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


registry = _load_registry_module()
register_source = registry.register_source
RegistrationResult = registry.RegistrationResult


# ---------------------------------------------------------------------------
# Helpers
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


def _make_registry(tmp: Path, content: str = _REGISTRY_HEADER) -> Path:
    path = tmp / "source-registry.md"
    path.write_text(content, encoding="utf-8")
    return path


def _parse_rows(text: str) -> list[dict[str, str]]:
    """Return parsed data rows from a registry file."""
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or cells[0] in {"Source ID", "---"} or set(cells[0]) == {"-"}:
            continue
        if len(cells) < 6:
            continue
        source_id, title, tier, status, derived_path, notes = cells[:6]
        if source_id and source_id != "-":
            rows.append({
                "source_id": source_id,
                "title": title,
                "tier": tier,
                "status": status,
                "derived_path": derived_path,
                "notes": notes,
            })
    return rows


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

class TestRegisterSourceSuccess(unittest.TestCase):

    def test_success_appends_row_to_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            result = register_source(
                source_id="test-source",
                title="Test Source",
                tier="reference",
                derived_path="-",
                registry_path=reg,
                format_has_locators=False,
            )
            self.assertTrue(result.ok)
            self.assertEqual([], result.missing)
            rows = _parse_rows(reg.read_text(encoding="utf-8"))
            self.assertEqual(1, len(rows))
            row = rows[0]
            self.assertEqual("test-source", row["source_id"])
            self.assertEqual("Test Source", row["title"])
            self.assertEqual("reference", row["tier"])
            self.assertEqual("needs-review", row["status"])
            self.assertEqual("-", row["derived_path"])

    def test_success_with_locator_stored_in_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            result = register_source(
                source_id="web-source",
                title="Web Source",
                tier="primary",
                derived_path="-",
                locator="https://example.com",
                registry_path=reg,
                format_has_locators=True,
            )
            self.assertTrue(result.ok)
            rows = _parse_rows(reg.read_text(encoding="utf-8"))
            self.assertEqual(1, len(rows))
            self.assertIn("https://example.com", rows[0]["notes"])

    def test_success_custom_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            result = register_source(
                source_id="active-source",
                title="Active Source",
                tier="secondary",
                derived_path="raw/derived/active-source",
                status="active",
                registry_path=reg,
                format_has_locators=False,
            )
            self.assertTrue(result.ok)
            rows = _parse_rows(reg.read_text(encoding="utf-8"))
            self.assertEqual("active", rows[0]["status"])

    def test_idempotent_update_in_place_no_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            # First registration
            register_source(
                source_id="my-source",
                title="My Source",
                tier="reference",
                derived_path="-",
                registry_path=reg,
                format_has_locators=False,
            )
            # Second registration with updated title
            result = register_source(
                source_id="my-source",
                title="My Source Updated",
                tier="primary",
                derived_path="-",
                registry_path=reg,
                format_has_locators=False,
            )
            self.assertTrue(result.ok)
            rows = _parse_rows(reg.read_text(encoding="utf-8"))
            # Only one row — no duplicate
            self.assertEqual(1, len(rows))
            self.assertEqual("My Source Updated", rows[0]["title"])
            self.assertEqual("primary", rows[0]["tier"])

    def test_multiple_distinct_sources_appended(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            for i in range(3):
                register_source(
                    source_id=f"source-{i}",
                    title=f"Source {i}",
                    tier="reference",
                    derived_path="-",
                    registry_path=reg,
                    format_has_locators=False,
                )
            rows = _parse_rows(reg.read_text(encoding="utf-8"))
            self.assertEqual(3, len(rows))
            ids = [r["source_id"] for r in rows]
            self.assertIn("source-0", ids)
            self.assertIn("source-1", ids)
            self.assertIn("source-2", ids)

    def test_all_tier_values_accepted(self):
        from tools.wiki_spec import ALLOWED_SOURCE_TIERS
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            for tier in sorted(ALLOWED_SOURCE_TIERS):
                result = register_source(
                    source_id=f"source-{tier}",
                    title=f"Source {tier}",
                    tier=tier,
                    derived_path="-",
                    registry_path=reg,
                    format_has_locators=False,
                )
                self.assertTrue(result.ok, f"Expected ok=True for tier {tier!r}")

    def test_new_registry_file_created_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = Path(tmp) / "new-registry.md"
            self.assertFalse(reg.exists())
            result = register_source(
                source_id="bootstrap-source",
                title="Bootstrap Source",
                tier="reference",
                derived_path="-",
                registry_path=reg,
                format_has_locators=False,
            )
            self.assertTrue(result.ok)
            self.assertTrue(reg.exists())
            rows = _parse_rows(reg.read_text(encoding="utf-8"))
            self.assertEqual(1, len(rows))
            self.assertEqual("bootstrap-source", rows[0]["source_id"])


# ---------------------------------------------------------------------------
# Failure: missing registration fields
# ---------------------------------------------------------------------------

class TestRegisterSourceMissingRegistration(unittest.TestCase):

    def _call(self, tmp: Path, **kwargs) -> RegistrationResult:
        defaults = dict(
            source_id="s",
            title="T",
            tier="reference",
            derived_path="-",
            registry_path=_make_registry(tmp),
            format_has_locators=False,
        )
        defaults.update(kwargs)
        return register_source(**defaults)

    def test_empty_source_id_returns_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._call(Path(tmp), source_id="")
            self.assertFalse(result.ok)
            self.assertIn("registration", result.missing)

    def test_whitespace_source_id_returns_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._call(Path(tmp), source_id="   ")
            self.assertFalse(result.ok)
            self.assertIn("registration", result.missing)

    def test_empty_title_returns_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._call(Path(tmp), title="")
            self.assertFalse(result.ok)
            self.assertIn("registration", result.missing)

    def test_empty_derived_path_returns_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._call(Path(tmp), derived_path="")
            self.assertFalse(result.ok)
            self.assertIn("registration", result.missing)

    def test_failure_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            original = reg.read_text(encoding="utf-8")
            result = self._call(Path(tmp), source_id="", registry_path=reg)
            self.assertFalse(result.ok)
            self.assertEqual(original, reg.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Failure: invalid tier
# ---------------------------------------------------------------------------

class TestRegisterSourceInvalidTier(unittest.TestCase):

    def test_unknown_tier_returns_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            result = register_source(
                source_id="s",
                title="T",
                tier="bogus-tier",
                derived_path="-",
                registry_path=reg,
                format_has_locators=False,
            )
            self.assertFalse(result.ok)
            self.assertIn("tier", result.missing)

    def test_empty_tier_returns_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            result = register_source(
                source_id="s",
                title="T",
                tier="",
                derived_path="-",
                registry_path=reg,
                format_has_locators=False,
            )
            self.assertFalse(result.ok)
            self.assertIn("tier", result.missing)

    def test_tier_failure_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            original = reg.read_text(encoding="utf-8")
            register_source(
                source_id="s",
                title="T",
                tier="invalid",
                derived_path="-",
                registry_path=reg,
                format_has_locators=False,
            )
            self.assertEqual(original, reg.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Failure: missing locator for locator-capable formats
# ---------------------------------------------------------------------------

class TestRegisterSourceMissingLocator(unittest.TestCase):

    def test_missing_locator_when_format_has_locators_returns_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            result = register_source(
                source_id="web-source",
                title="Web Source",
                tier="reference",
                derived_path="-",
                locator=None,
                registry_path=reg,
                format_has_locators=True,
            )
            self.assertFalse(result.ok)
            self.assertIn("locator", result.missing)

    def test_empty_locator_when_format_has_locators_returns_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            result = register_source(
                source_id="web-source",
                title="Web Source",
                tier="reference",
                derived_path="-",
                locator="",
                registry_path=reg,
                format_has_locators=True,
            )
            self.assertFalse(result.ok)
            self.assertIn("locator", result.missing)

    def test_locator_not_required_when_format_has_no_locators(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            result = register_source(
                source_id="pdf-source",
                title="PDF Source",
                tier="primary",
                derived_path="-",
                locator=None,
                registry_path=reg,
                format_has_locators=False,
            )
            self.assertTrue(result.ok)
            self.assertNotIn("locator", result.missing)

    def test_locator_failure_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            original = reg.read_text(encoding="utf-8")
            register_source(
                source_id="web-source",
                title="Web Source",
                tier="reference",
                derived_path="-",
                locator=None,
                registry_path=reg,
                format_has_locators=True,
            )
            self.assertEqual(original, reg.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Multiple failures in one call
# ---------------------------------------------------------------------------

class TestRegisterSourceMultipleFailures(unittest.TestCase):

    def test_bad_tier_and_missing_locator_both_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = _make_registry(Path(tmp))
            result = register_source(
                source_id="s",
                title="T",
                tier="invalid",
                derived_path="-",
                locator=None,
                registry_path=reg,
                format_has_locators=True,
            )
            self.assertFalse(result.ok)
            self.assertIn("tier", result.missing)
            self.assertIn("locator", result.missing)


if __name__ == "__main__":
    unittest.main()
