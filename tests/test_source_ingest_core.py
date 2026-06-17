"""Tests for tools/source-ingest/core.py (issue #60).

Covers:
- SOURCE_ID_RE pattern contracts
- validate_source_id (valid slugs pass, invalid slugs raise SystemExit)
- wire_registry (returns callable, raises ImportError when registry missing)
- derived_output_path (canonical path string construction)
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "tools" / "source-ingest" / "core.py"


def _load_core():
    """Load core.py using importlib so the test is path-independent."""
    spec = importlib.util.spec_from_file_location("_si_core", CORE_PATH)
    assert spec and spec.loader, f"Could not load {CORE_PATH}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_si_core"] = mod
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


core = _load_core()


class TestSourceIdRegex(unittest.TestCase):
    """SOURCE_ID_RE contract: lowercase-alpha-numeric with internal dashes."""

    def _match(self, slug: str) -> bool:
        return bool(core.SOURCE_ID_RE.match(slug))

    # --- valid slugs ---
    def test_simple_word_matches(self):
        self.assertTrue(self._match("mysource"))

    def test_word_with_digits_matches(self):
        self.assertTrue(self._match("source2024"))

    def test_word_with_internal_dash_matches(self):
        self.assertTrue(self._match("my-source"))

    def test_multi_dash_matches(self):
        self.assertTrue(self._match("my-source-2024"))

    def test_two_char_minimum_matches(self):
        self.assertTrue(self._match("ab"))

    def test_digit_start_matches(self):
        self.assertTrue(self._match("2024-paper"))

    # --- invalid slugs ---
    def test_uppercase_does_not_match(self):
        self.assertFalse(self._match("MySource"))

    def test_leading_dash_does_not_match(self):
        self.assertFalse(self._match("-my-source"))

    def test_trailing_dash_does_not_match(self):
        self.assertFalse(self._match("my-source-"))

    def test_underscore_does_not_match(self):
        self.assertFalse(self._match("my_source"))

    def test_pipe_does_not_match(self):
        self.assertFalse(self._match("my|source"))

    def test_space_does_not_match(self):
        self.assertFalse(self._match("my source"))

    def test_single_char_does_not_match(self):
        self.assertFalse(self._match("a"))

    def test_empty_string_does_not_match(self):
        self.assertFalse(self._match(""))


class TestValidateSourceId(unittest.TestCase):
    """validate_source_id raises SystemExit for bad slugs; passes for valid ones."""

    def test_valid_slug_passes_silently(self):
        # Should not raise.
        core.validate_source_id("my-source")

    def test_valid_slug_with_digits_passes(self):
        core.validate_source_id("paper-2024-v2")

    def test_invalid_slug_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            core.validate_source_id("Bad_ID")

    def test_empty_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            core.validate_source_id("")

    def test_leading_dash_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            core.validate_source_id("-slug")

    def test_uppercase_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            core.validate_source_id("MySlug")

    def test_error_message_is_informative(self):
        with self.assertRaises(SystemExit) as ctx:
            core.validate_source_id("Bad_ID")
        msg = str(ctx.exception)
        # Message must mention the character rules.
        self.assertIn("lowercase", msg.lower())


class TestWireRegistry(unittest.TestCase):
    """wire_registry returns a callable; raises ImportError when registry missing."""

    def test_returns_callable(self):
        fn = core.wire_registry()
        self.assertTrue(callable(fn))

    def test_returned_function_is_register_source(self):
        fn = core.wire_registry()
        # The function signature must accept the keyword arguments that
        # register_source expects.  We verify by checking its __code__ for
        # 'source_id' in co_varnames (or via __code__.co_varnames).
        import inspect
        sig = inspect.signature(fn)
        self.assertIn("source_id", sig.parameters)
        self.assertIn("registry_path", sig.parameters)

    def test_raises_import_error_when_registry_missing(self, monkeypatch=None):
        """Temporarily rename registry.py to verify error handling."""
        registry_path = ROOT / "tools" / "source-ingest" / "registry.py"
        temp_name = registry_path.parent / "_registry_hidden_for_test.py"
        registry_path.rename(temp_name)
        try:
            # Reload core to force a fresh wire_registry call without cache.
            spec = importlib.util.spec_from_file_location("_si_core_fresh", CORE_PATH)
            fresh_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fresh_mod)  # type: ignore[attr-defined]
            with self.assertRaises(ImportError):
                fresh_mod.wire_registry()
        finally:
            temp_name.rename(registry_path)

    def test_wire_registry_result_writes_registry(self):
        """End-to-end smoke: the returned callable writes a valid registry row."""
        register_source = core.wire_registry()
        with tempfile.TemporaryDirectory() as tmp:
            reg = Path(tmp) / "meta" / "source-registry.md"
            reg.parent.mkdir()
            reg.write_text(
                "# Source Registry\n\n"
                "| Source ID | Title | Tier | Status | Derived Path | Notes |\n"
                "| --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            result = register_source(
                source_id="test-core",
                title="Core Test Source",
                tier="primary",
                derived_path="raw/derived/test-core",
                locator="https://example.com/test",
                format_has_locators=True,
                registry_path=reg,
            )
            self.assertTrue(result.ok)
            text = reg.read_text(encoding="utf-8")
            self.assertIn("test-core", text)
            self.assertIn("Core Test Source", text)


class TestDerivedOutputPath(unittest.TestCase):
    """derived_output_path builds canonical <output_root>/<source_id> strings."""

    def test_relative_root_string(self):
        result = core.derived_output_path("raw/derived", "my-source")
        self.assertEqual(result, "raw/derived/my-source")

    def test_relative_root_path_object(self):
        result = core.derived_output_path(Path("raw/derived"), "my-source")
        self.assertEqual(result, "raw/derived/my-source")

    def test_absolute_root_string(self):
        result = core.derived_output_path("/tmp/wiki/raw/derived", "alpha")
        self.assertEqual(result, "/tmp/wiki/raw/derived/alpha")

    def test_output_contains_source_id(self):
        result = core.derived_output_path("out", "paper-2024")
        self.assertIn("paper-2024", result)

    def test_output_starts_with_root(self):
        result = core.derived_output_path("raw/derived", "source-a")
        self.assertTrue(result.startswith("raw/derived"))

    def test_path_separator_is_forward_slash(self):
        result = core.derived_output_path("raw/derived", "source-b")
        self.assertIn("/", result)
        self.assertNotIn("\\", result)


if __name__ == "__main__":
    unittest.main()
