"""Tests for tools/checks/identity.py — identity consistency validator.

Verifies three behavioural properties:
  1. A surface containing a non-canonical owner slug produces an error that
     names the surface and the expected canonical home.
  2. A surface containing only canonical references produces no errors.
  3. Content under the vendored-template tree does NOT trigger a false failure
     (the check only inspects the two declared trust surfaces).
"""

from __future__ import annotations

import json
import types
import unittest
from pathlib import Path
import tempfile
import os


class _FakeModel:
    """Minimal stand-in for tools.wiki_model.RepoModel."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.artifacts = []
        self.sources: dict = {}


class TestIdentityCheck(unittest.TestCase):
    # ------------------------------------------------------------------ helpers

    def _import_check(self):
        """Import identity.py whether the cwd is the repo root or anywhere."""
        import importlib
        try:
            from tools.checks import identity
        except ImportError:
            import sys
            repo_root = Path(__file__).resolve().parents[1]
            sys.path.insert(0, str(repo_root / "tools"))
            from checks import identity
        return identity

    def _run(self, tmp: Path, identity_mod) -> list[str]:
        errors: list[str] = []
        model = _FakeModel(root=tmp)
        identity_mod.check(model, errors)
        return errors

    def _make_surface(self, tmp: Path, rel: str, content: str) -> None:
        target = tmp / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    # ------------------------------------------------------------------ tests

    def test_non_canonical_owner_in_readme_produces_error(self):
        identity = self._import_check()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            self._make_surface(
                tmp,
                "README.md",
                "Install: `uvx --from git+https://github.com/badactor/llm-wiki-starter foo`\n",
            )
            errors = self._run(tmp, identity)
        self.assertTrue(errors, "Expected at least one error for non-canonical owner")
        # Error must name the surface file
        self.assertIn("README.md", errors[0])
        # Error must name the canonical home
        self.assertIn(identity.CANONICAL_HOME, errors[0])
        # Error must mention the offending slug
        self.assertIn("badactor/llm-wiki-starter", errors[0])

    def test_non_canonical_owner_in_plugin_json_produces_error(self):
        identity = self._import_check()
        rel_path = "plugins/llm-wiki/.codex-plugin/plugin.json"
        payload = json.dumps(
            {"homepage": "https://github.com/someoneelse/llm-wiki-starter"}
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            self._make_surface(tmp, rel_path, payload)
            errors = self._run(tmp, identity)
        self.assertTrue(errors, "Expected an error for non-canonical owner in plugin.json")
        self.assertIn("plugin.json", errors[0])
        self.assertIn(identity.CANONICAL_HOME, errors[0])

    def test_canonical_references_produce_no_errors(self):
        identity = self._import_check()
        readme_content = (
            "uvx --from git+https://github.com/drkolesnikov/llm-wiki-starter llm-wiki init\n"
        )
        plugin_content = json.dumps(
            {"homepage": "https://github.com/drkolesnikov/llm-wiki-starter"}
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            self._make_surface(tmp, "README.md", readme_content)
            self._make_surface(
                tmp, "plugins/llm-wiki/.codex-plugin/plugin.json", plugin_content
            )
            errors = self._run(tmp, identity)
        self.assertEqual(errors, [], f"Expected no errors; got: {errors}")

    def test_missing_surfaces_do_not_raise(self):
        """A repo with neither surface present should silently produce no errors."""
        identity = self._import_check()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            errors = self._run(tmp, identity)
        self.assertEqual(errors, [])

    def test_vendored_template_tree_is_not_scanned(self):
        """Content under src/llm_wiki_wizard/templates/ must not trigger a false failure."""
        identity = self._import_check()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            # Plant non-canonical content deep in the template tree only —
            # neither declared surface exists.
            template_path = (
                tmp / "src" / "llm_wiki_wizard" / "templates" / "wiki"
                / "tools" / "checks" / "identity.py"
            )
            template_path.parent.mkdir(parents=True, exist_ok=True)
            template_path.write_text(
                "CANONICAL_HOME = 'otherowner/llm-wiki-starter'\n", encoding="utf-8"
            )
            errors = self._run(tmp, identity)
        self.assertEqual(
            errors,
            [],
            "Vendored template content must not be inspected by the identity check",
        )

    def test_multiple_non_canonical_references_all_reported(self):
        """Every offending slug in a surface should produce its own error entry."""
        identity = self._import_check()
        content = (
            "See https://github.com/alice/llm-wiki-starter and "
            "https://github.com/bob/llm-wiki-starter\n"
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            self._make_surface(tmp, "README.md", content)
            errors = self._run(tmp, identity)
        self.assertEqual(len(errors), 2, f"Expected 2 errors; got: {errors}")
        owners = {e for e in errors if "alice" in e or "bob" in e}
        self.assertEqual(len(owners), 2)

    def test_canonical_constant_value(self):
        """CANONICAL_HOME must equal the expected slug string."""
        identity = self._import_check()
        self.assertEqual(identity.CANONICAL_HOME, "drkolesnikov/llm-wiki-starter")


if __name__ == "__main__":
    unittest.main()
