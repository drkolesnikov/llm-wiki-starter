"""Shared source-ingest core — validators, registry wiring, and scaffold helpers.

This module is the single source of truth for patterns that are (or would be)
duplicated across every format adapter (pdf, epub, web, …).  Each adapter
imports from here instead of re-implementing the same logic.

Public surface
--------------
SOURCE_ID_RE        — compiled regex for valid source-id slugs.
validate_source_id  — raise SystemExit on invalid slug (replaces per-adapter
                      ``require_source_id`` / ``SOURCE_ID_RE.match`` guards).
wire_registry       — load ``registry.register_source`` via a regular import
                      (replaces the importlib boilerplate triplicated across
                      pdf/epub/web adapters).
derived_output_path — build the canonical ``<output_root>/<source_id>`` path
                      string used in registry rows.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Source-id validation
# ---------------------------------------------------------------------------

# Slug rules: lowercase letters/digits, internal dashes allowed, must start
# and end with a letter or digit (minimum two characters).
SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


def validate_source_id(source_id: str) -> None:
    """Raise ``SystemExit`` when *source_id* does not match :data:`SOURCE_ID_RE`.

    Parameters
    ----------
    source_id:
        The candidate slug to validate.

    Raises
    ------
    SystemExit
        With a human-readable message when the slug is invalid.
    """
    if not SOURCE_ID_RE.match(source_id):
        raise SystemExit(
            "source-id must use lowercase letters, digits, and dashes "
            "(e.g. 'my-source-2024')."
        )


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------

def wire_registry():
    """Return the ``register_source`` callable from ``registry.py``.

    Locates ``registry.py`` relative to this file
    (``tools/source-ingest/registry.py``), ensures its directory is on
    ``sys.path``, imports it with the standard import machinery, and returns
    its ``register_source`` function.

    This replaces the ``importlib.util`` boilerplate that previously appeared
    verbatim in each format adapter.

    Returns
    -------
    Callable
        The ``register_source`` function from the registry module.

    Raises
    ------
    ImportError
        When the registry module cannot be located or loaded.
    """
    registry_path = Path(__file__).resolve().parent / "registry.py"
    if not registry_path.exists():
        raise ImportError(
            f"Could not find source registry at {registry_path}. "
            "Ensure tools/source-ingest/registry.py is present."
        )

    # Ensure the source-ingest directory is importable so that registry.py
    # can, in turn, import from tools/ (it adjusts sys.path itself).
    si_dir = str(registry_path.parent)
    if si_dir not in sys.path:
        sys.path.insert(0, si_dir)

    # Use standard import machinery — avoids the importlib.util dance.
    import importlib
    _mod = importlib.import_module("registry")
    register_source = getattr(_mod, "register_source", None)
    if register_source is None:
        raise ImportError(
            f"registry module at {registry_path} has no 'register_source' attribute."
        )
    return register_source


# ---------------------------------------------------------------------------
# Scaffold helpers
# ---------------------------------------------------------------------------

def derived_output_path(output_root: str | Path, source_id: str) -> str:
    """Return the canonical registry ``derived_path`` string.

    The string is relative (e.g. ``"raw/derived/my-source"``) and suitable for
    the *derived_path* argument of ``register_source``.

    Parameters
    ----------
    output_root:
        The ``--output-root`` value (may be absolute or relative).
    source_id:
        The validated source slug.

    Returns
    -------
    str
        A POSIX-style relative path string: ``"<output_root>/<source_id>"``.
    """
    root = Path(output_root)
    # Keep the value relative if the caller passed a relative root; otherwise
    # use as-is.  The registry stores paths that make sense within the wiki.
    return f"{root}/{source_id}"
