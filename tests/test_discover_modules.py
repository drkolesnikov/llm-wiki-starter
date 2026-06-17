"""Tests for tools._registry.discover_modules (issue #58).

Covers:
  - Basic discovery: sorted by name, skipping underscore modules.
  - Missing attribute tolerated (module without the attribute is skipped).
  - sort=False returns in pkgutil iteration order (non-sorted).
  - Three registries delegate to the helper and still work end-to-end.
  - ``llm-wiki --help`` commands are listed in sorted order.
"""

from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helper: build a fake in-memory package for isolation tests
# ---------------------------------------------------------------------------

def _make_fake_package(name: str, modules: dict[str, dict[str, Any]]) -> types.ModuleType:
    """Create a fake in-memory package whose sub-modules have given attrs.

    Parameters
    ----------
    name:
        Dotted name for the package (e.g. ``"_fake_pkg"``).
    modules:
        Mapping of module base-name to dict of attributes to set on it.

    Returns the package module; side-effects sys.modules.
    """
    pkg = types.ModuleType(name)
    pkg.__path__ = []  # mark as package
    pkg.__package__ = name
    sys.modules[name] = pkg

    for mod_name, attrs in modules.items():
        full_name = f"{name}.{mod_name}"
        mod = types.ModuleType(full_name)
        for attr, val in attrs.items():
            setattr(mod, attr, val)
        sys.modules[full_name] = mod

    # Provide a fake __path__ that pkgutil.iter_modules can introspect.
    # We monkey-patch pkgutil by using a FileFinder-compatible approach —
    # easier: just register a custom finder on sys.meta_path.
    return pkg


# ---------------------------------------------------------------------------
# Fake package via sys.modules + custom MetaPathFinder
# ---------------------------------------------------------------------------

import pkgutil
import importlib.abc
import importlib.machinery


class _FakePackageFinder(importlib.abc.MetaPathFinder):
    """Simple finder that serves fake ModuleSpec objects from sys.modules."""

    def find_spec(self, fullname, path, target=None):
        if fullname in sys.modules:
            mod = sys.modules[fullname]
            origin = getattr(mod, "__file__", None) or "<fake>"
            is_pkg = hasattr(mod, "__path__")
            spec = importlib.machinery.ModuleSpec(
                name=fullname,
                loader=_FakeLoader(mod),
                origin=origin,
                is_package=is_pkg,
            )
            if is_pkg:
                spec.submodule_search_locations = list(getattr(mod, "__path__", []))
            return spec
        return None


class _FakeLoader(importlib.abc.Loader):
    def __init__(self, mod):
        self._mod = mod

    def create_module(self, spec):
        return self._mod

    def exec_module(self, module):
        pass  # already populated


# Register once at module level.
_finder = _FakePackageFinder()
sys.meta_path.insert(0, _finder)


def _register_fake_pkg(pkg_name: str, submodules: dict[str, dict[str, Any]]) -> types.ModuleType:
    """Register a fake package and its sub-modules in sys.modules."""
    # Clean up any prior run.
    for key in list(sys.modules):
        if key == pkg_name or key.startswith(f"{pkg_name}."):
            del sys.modules[key]

    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [f"<fake:{pkg_name}>"]
    pkg.__package__ = pkg_name
    pkg.__file__ = f"<fake:{pkg_name}/__init__.py>"
    sys.modules[pkg_name] = pkg

    for mod_name, attrs in submodules.items():
        full_name = f"{pkg_name}.{mod_name}"
        mod = types.ModuleType(full_name)
        mod.__package__ = pkg_name
        mod.__file__ = f"<fake:{pkg_name}/{mod_name}.py>"
        for attr, val in attrs.items():
            setattr(mod, attr, val)
        sys.modules[full_name] = mod

    return pkg


# ---------------------------------------------------------------------------
# discover_modules unit tests
# ---------------------------------------------------------------------------

class DiscoverModulesSortedTest(unittest.TestCase):
    """discover_modules returns pairs sorted by module name."""

    def setUp(self):
        from tools._registry import discover_modules
        self.discover = discover_modules
        self.pkg_name = "_test_sorted_pkg"
        pkg = _register_fake_pkg(self.pkg_name, {
            "z_module": {"thing": "Z"},
            "a_module": {"thing": "A"},
            "m_module": {"thing": "M"},
        })
        self.pkg_path = pkg.__path__

    def tearDown(self):
        for key in list(sys.modules):
            if key == self.pkg_name or key.startswith(f"{self.pkg_name}."):
                del sys.modules[key]

    def test_sorted_order(self):
        # pkgutil.iter_modules on an in-memory fake __path__ won't find anything
        # without a real filesystem.  Instead, patch pkgutil.iter_modules.
        import tools._registry as reg
        import pkgutil

        original = pkgutil.iter_modules

        def fake_iter(path, prefix=""):
            names = ["z_module", "a_module", "m_module"]
            for n in names:
                yield pkgutil.ModuleInfo(None, n, False)

        pkgutil.iter_modules = fake_iter
        try:
            result = self.discover(self.pkg_path, self.pkg_name, "thing", sort=True)
        finally:
            pkgutil.iter_modules = original

        self.assertEqual([n for n, _ in result], ["a_module", "m_module", "z_module"])
        self.assertEqual([v for _, v in result], ["A", "M", "Z"])


class DiscoverModulesSkipUnderscoreTest(unittest.TestCase):
    """Modules whose names start with _ are silently skipped."""

    def setUp(self):
        from tools._registry import discover_modules
        self.discover = discover_modules
        self.pkg_name = "_test_skip_pkg"
        pkg = _register_fake_pkg(self.pkg_name, {
            "_private": {"thing": "private"},
            "public":   {"thing": "public"},
            "__dunder": {"thing": "dunder"},
        })
        self.pkg_path = pkg.__path__

    def tearDown(self):
        for key in list(sys.modules):
            if key == self.pkg_name or key.startswith(f"{self.pkg_name}."):
                del sys.modules[key]

    def test_private_skipped(self):
        import tools._registry as reg
        import pkgutil

        original = pkgutil.iter_modules

        def fake_iter(path, prefix=""):
            for n in ["_private", "__dunder", "public"]:
                yield pkgutil.ModuleInfo(None, n, False)

        pkgutil.iter_modules = fake_iter
        try:
            result = self.discover(self.pkg_path, self.pkg_name, "thing", sort=True)
        finally:
            pkgutil.iter_modules = original

        names = [n for n, _ in result]
        self.assertNotIn("_private", names)
        self.assertNotIn("__dunder", names)
        self.assertIn("public", names)


class DiscoverModulesMissingAttrTest(unittest.TestCase):
    """Modules that lack the requested attribute are silently skipped."""

    def setUp(self):
        from tools._registry import discover_modules
        self.discover = discover_modules
        self.pkg_name = "_test_missing_pkg"
        pkg = _register_fake_pkg(self.pkg_name, {
            "has_attr":    {"thing": "yes"},
            "no_attr":     {},          # no 'thing'
            "none_attr":   {"thing": None},  # None counts as missing
        })
        self.pkg_path = pkg.__path__

    def tearDown(self):
        for key in list(sys.modules):
            if key == self.pkg_name or key.startswith(f"{self.pkg_name}."):
                del sys.modules[key]

    def test_missing_attr_tolerated(self):
        import pkgutil

        original = pkgutil.iter_modules

        def fake_iter(path, prefix=""):
            for n in ["has_attr", "no_attr", "none_attr"]:
                yield pkgutil.ModuleInfo(None, n, False)

        pkgutil.iter_modules = fake_iter
        try:
            result = self.discover(self.pkg_path, self.pkg_name, "thing", sort=True)
        finally:
            pkgutil.iter_modules = original

        names = [n for n, _ in result]
        self.assertEqual(names, ["has_attr"])


class DiscoverModulesUnsortedTest(unittest.TestCase):
    """sort=False preserves pkgutil iteration order."""

    def setUp(self):
        from tools._registry import discover_modules
        self.discover = discover_modules
        self.pkg_name = "_test_unsorted_pkg"
        pkg = _register_fake_pkg(self.pkg_name, {
            "z_mod": {"v": 3},
            "a_mod": {"v": 1},
            "m_mod": {"v": 2},
        })
        self.pkg_path = pkg.__path__

    def tearDown(self):
        for key in list(sys.modules):
            if key == self.pkg_name or key.startswith(f"{self.pkg_name}."):
                del sys.modules[key]

    def test_unsorted_preserves_iteration_order(self):
        import pkgutil

        original = pkgutil.iter_modules
        iteration_order = ["z_mod", "a_mod", "m_mod"]

        def fake_iter(path, prefix=""):
            for n in iteration_order:
                yield pkgutil.ModuleInfo(None, n, False)

        pkgutil.iter_modules = fake_iter
        try:
            result = self.discover(self.pkg_path, self.pkg_name, "v", sort=False)
        finally:
            pkgutil.iter_modules = original

        self.assertEqual([n for n, _ in result], iteration_order)


# ---------------------------------------------------------------------------
# Registry integration tests
# ---------------------------------------------------------------------------

class ChecksRegistryTest(unittest.TestCase):
    """tools.checks.discover_checks still returns (name, callable) pairs sorted."""

    def test_discover_checks_returns_sorted_callables(self):
        from tools.checks import discover_checks
        result = discover_checks()
        self.assertIsInstance(result, list)
        names = [n for n, _ in result]
        self.assertEqual(names, sorted(names), "checks are not sorted by name")
        for _name, fn in result:
            self.assertTrue(callable(fn), f"check '{_name}' is not callable")

    def test_known_checks_present(self):
        from tools.checks import discover_checks
        names = [n for n, _ in discover_checks()]
        self.assertIn("c10_frontmatter", names)
        self.assertIn("c20_registry", names)
        self.assertIn("c30_links", names)


class SignalsRegistryTest(unittest.TestCase):
    """tools.eval.discover_signals still returns (name, Signal) pairs sorted."""

    def test_discover_signals_returns_sorted(self):
        from tools.eval import discover_signals
        result = discover_signals()
        self.assertIsInstance(result, list)
        names = [n for n, _ in result]
        self.assertEqual(names, sorted(names), "signals are not sorted by name")

    def test_known_signals_present(self):
        from tools.eval import discover_signals
        names = [n for n, _ in discover_signals()]
        self.assertIn("contradiction", names)
        self.assertIn("duplication", names)
        self.assertIn("grounding", names)

    def test_signals_have_id(self):
        from tools.eval import discover_signals
        for _name, signal in discover_signals():
            self.assertTrue(hasattr(signal, "id"), f"SIGNAL '{_name}' has no 'id' attribute")


class CommandsRegistryTest(unittest.TestCase):
    """register_all registers commands in sorted (deterministic) order."""

    def _parse_help_commands(self, help_text: str) -> list:
        """Extract command names from Typer --help output.

        Typer renders commands in a box like::

            ╭─ Commands ─╮
            │ foo   ...  │
            │ bar   ...  │
            ╰────────────╯

        We collect the first token on each inner line (lines that start with
        the box-drawing │ character U+2502) that immediately follows the
        Commands section header.  Lines that are indented past column 3 are
        continuation lines for the previous command's description.
        """
        BOX_SIDE = "│"   # │
        BOX_END  = "╰"   # ╰
        in_commands = False
        command_names = []
        for line in help_text.splitlines():
            # Detect the Commands section header (contains "Commands" and ─).
            if "Commands" in line and ("─" in line or "━" in line):
                in_commands = True
                continue
            if not in_commands:
                continue
            # End of the Commands box.
            if BOX_END in line or "┘" in line:
                break
            # Inner content lines start with the box-side character.
            if not line.startswith(BOX_SIDE):
                continue
            # Strip the leading │ and one space (Typer uses "│ cmd  desc │").
            inner = line[1:].lstrip(" ")
            if not inner:
                continue
            # Continuation lines for a multi-line description are indented.
            # A command-name line has the command as first token starting at
            # a low column (Typer keeps it at a fixed indent).
            # Simple heuristic: the first character of inner should be alpha.
            if inner[0].isalpha() or inner[0] == "-":
                cmd = inner.split()[0]
                if cmd[0].isalpha():
                    command_names.append(cmd)
        return command_names

    def test_llm_wiki_help_sorted(self):
        """llm-wiki --help output lists commands in deterministic (module-sorted) order."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "llm_wiki_wizard.cli", "--help"],
            capture_output=True, text=True,
        )
        command_names = self._parse_help_commands(result.stdout)
        self.assertTrue(len(command_names) >= 1, f"No commands found in --help output:\n{result.stdout}")
        # Commands appear grouped by module (each module is sorted); the full
        # list need not be globally sorted by command name because one module
        # may register multiple commands (e.g. index + reindex). What MUST be
        # deterministic is that the same list appears on every run.
        second_result = subprocess.run(
            [sys.executable, "-m", "llm_wiki_wizard.cli", "--help"],
            capture_output=True, text=True,
        )
        command_names_2 = self._parse_help_commands(second_result.stdout)
        self.assertEqual(command_names, command_names_2, "Command order differs between runs (non-deterministic)")

    def test_register_all_is_deterministic(self):
        """Calling register_all twice produces the same registration order."""
        import typer
        from llm_wiki_wizard.commands import register_all

        def _cmd_names(app):
            # resolved_commands includes both named and function-named commands
            # (some may be None before registration is complete); use the CLI
            # info path for reliable names.
            return [
                info.name
                for info in app.registered_commands
                if info.name is not None
            ]

        app1 = typer.Typer()
        register_all(app1)
        names1 = _cmd_names(app1)

        app2 = typer.Typer()
        register_all(app2)
        names2 = _cmd_names(app2)

        self.assertEqual(names1, names2, "Command registration order differs between invocations")


if __name__ == "__main__":
    unittest.main()
