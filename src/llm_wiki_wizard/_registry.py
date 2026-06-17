"""Shared auto-discovery helper for plugin-style package registries.

Usage::

    from llm_wiki_wizard._registry import discover_modules

    # Returns [(name, obj), ...] sorted by module name, skipping _ prefixes.
    pairs = discover_modules(
        path=__path__,          # pkgutil path of the containing package
        pkg_name=__name__,      # dotted name for importlib.import_module
        attribute="register",   # module-level attr to collect
        sort=True,              # optional; True is the default
    )

Modules that lack the requested attribute are silently skipped (tolerated),
so partially-implemented modules never break the whole suite.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any, List, Tuple


def discover_modules(
    path,
    pkg_name: str,
    attribute: str,
    *,
    sort: bool = True,
) -> List[Tuple[str, Any]]:
    """Return ``(module_name, attribute_value)`` pairs from a package.

    Parameters
    ----------
    path:
        The ``__path__`` of the package to scan (passed directly to
        :func:`pkgutil.iter_modules`).
    pkg_name:
        The dotted package name used to build fully-qualified module names for
        :func:`importlib.import_module` (typically the caller's ``__name__``).
    attribute:
        The module-level attribute name to collect from each discovered module.
    sort:
        When ``True`` (default) modules are yielded in ascending name order,
        making discovery fully deterministic.  Pass ``False`` only when order
        is genuinely irrelevant to the caller.

    Returns
    -------
    list of (name, value)
        One entry per module that (a) does not start with ``_`` and (b)
        exposes a non-``None`` value for *attribute*.
    """

    module_infos = pkgutil.iter_modules(path)
    if sort:
        module_infos = sorted(module_infos, key=lambda m: m.name)

    discovered: List[Tuple[str, Any]] = []
    for module_info in module_infos:
        name = module_info.name
        if name.startswith("_"):
            continue
        module = importlib.import_module(f"{pkg_name}.{name}")
        value = getattr(module, attribute, None)
        if value is not None:
            discovered.append((name, value))
    return discovered
