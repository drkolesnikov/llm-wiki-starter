#!/usr/bin/env python3
"""Auto-discovered structural-check registry for the wiki validator.

Each module in this package exposes a module-level callable::

    def check(model, errors) -> None: ...

where ``model`` is the :class:`tools.wiki_model.RepoModel` parsed once per run
and ``errors`` is a list the check appends human-readable strings to. The
validator discovers every sibling module here and runs their ``check``
functions in **sorted filename order**, so report and error text stay
deterministic. Adding a new structural check is therefore add-a-file: drop a
``*.py`` module exposing ``check`` into this directory; no edit to
``validate_repo.py`` is required.

Modules whose names start with ``_`` are treated as private helpers and are
skipped by discovery.
"""

from __future__ import annotations

from typing import Callable, List, Tuple

try:  # script invocation: ``tools/`` is on sys.path[0]
    from _registry import discover_modules
except ImportError:  # imported as ``tools.checks``
    from tools._registry import discover_modules


# A discovered check: (module_name, check_callable).
DiscoveredCheck = Tuple[str, Callable[[object, List[str]], None]]


def discover_checks() -> List[DiscoveredCheck]:
    """Return ``(name, check)`` pairs for every check module, sorted by name.

    Discovery is deterministic: modules are imported in ascending filename
    order and only those exposing a callable ``check`` attribute are included.
    Private modules (leading underscore) are ignored.
    """

    return discover_modules(__path__, __name__, "check", sort=True)


def run_checks(model: object, errors: List[str]) -> None:
    """Run every discovered check in sorted order, accumulating ``errors``."""

    for _name, check in discover_checks():
        check(model, errors)
