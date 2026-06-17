"""Shared source-registration module for all ingest paths.

Usage
-----
Call ``register_source(...)`` from any ingest script (PDF, EPUB, web, …) to
atomically validate and write a row to ``meta/source-registry.md``.

This is library code only — no CLI entry point.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Locate tools/ so we can import wiki_spec even when this module is imported
# from an arbitrary working directory.
# ---------------------------------------------------------------------------
_TOOLS_DIR = Path(__file__).resolve().parents[2]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from tools.wiki_spec import ALLOWED_SOURCE_TIERS  # noqa: E402


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

@dataclass
class RegistrationResult:
    """Outcome of a ``register_source`` call.

    Attributes
    ----------
    ok:
        ``True`` when the registry was updated successfully.
    missing:
        Itemised list of validation failures.  Each entry is one of:
        ``"registration"`` (empty source_id / title / derived_path),
        ``"tier"`` (value not in ALLOWED_SOURCE_TIERS), or
        ``"locator"`` (locator required but absent).
    """

    ok: bool
    missing: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipe-table helpers
# ---------------------------------------------------------------------------

_HEADER = "| Source ID | Title | Tier | Status | Derived Path | Notes |"
_SEPARATOR = "| --- | --- | --- | --- | --- | --- |"


def _row(source_id: str, title: str, tier: str, status: str,
         derived_path: str, notes: str) -> str:
    return f"| {source_id} | {title} | {tier} | {status} | {derived_path} | {notes} |"


def _parse_row(line: str) -> tuple[str, ...] | None:
    """Return a 6-tuple of cell values for a data row, or None."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    cells = [c.strip() for c in stripped.strip("|").split("|")]
    if not cells or cells[0] in {"Source ID", "---"} or set(cells[0]) == {"-"}:
        return None
    if len(cells) < 6:
        return None
    return tuple(cells[:6])


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def register_source(
    *,
    source_id: str,
    title: str,
    tier: str,
    derived_path: str,
    status: str = "needs-review",
    locator: str | None = None,
    format_has_locators: bool,
    registry_path: Path,
) -> RegistrationResult:
    """Validate and register a source in the registry pipe-table.

    Parameters
    ----------
    source_id:
        Unique slug identifier for the source (non-empty, no pipes).
    title:
        Human-readable title for the source (non-empty).
    tier:
        Must be a value in ``ALLOWED_SOURCE_TIERS``.
    derived_path:
        Relative path to the derived output directory, or ``"-"`` when none.
    status:
        One of the allowed wiki statuses.  Defaults to ``"needs-review"``.
    locator:
        URL or other locator for the source.  Required when
        ``format_has_locators`` is ``True``; ignored when ``False``.
    format_has_locators:
        Pass ``True`` for formats where a URL/locator is expected (e.g. web).
        Pass ``False`` for formats where a locator is not applicable (e.g. a
        local PDF that has already been ingested).
    registry_path:
        Absolute or relative path to ``meta/source-registry.md``.

    Returns
    -------
    RegistrationResult
        ``ok=True`` and the registry file updated on success;
        ``ok=False`` with an itemised ``missing`` list on any validation error
        (the file is **not** modified in that case).
    """
    missing: list[str] = []

    # --- validate registration fields ---
    if not source_id or not source_id.strip():
        missing.append("registration")
    elif not title or not title.strip():
        missing.append("registration")
    elif not derived_path or not derived_path.strip():
        missing.append("registration")

    # --- validate tier ---
    if tier not in ALLOWED_SOURCE_TIERS:
        missing.append("tier")

    # --- validate locator ---
    if format_has_locators and not locator:
        missing.append("locator")

    if missing:
        return RegistrationResult(ok=False, missing=missing)

    # --- build the Notes cell --------------------------------------------------
    # If a locator was provided, include it in Notes; otherwise use "-".
    if locator:
        notes = f"URL: {locator}"
    else:
        notes = "-"

    new_row = _row(source_id, title, tier, status, derived_path, notes)

    # --- read existing registry ---
    registry_path = Path(registry_path)
    if registry_path.exists():
        text = registry_path.read_text(encoding="utf-8")
    else:
        # Bootstrap a minimal registry file.
        text = (
            "# Source Registry\n\n"
            "Register sources before they support durable knowledge artifacts.\n\n"
            f"{_HEADER}\n"
            f"{_SEPARATOR}\n"
        )

    lines = text.splitlines(keepends=True)

    # --- check for existing row with same source_id (update in place) ---
    updated = False
    for i, line in enumerate(lines):
        parsed = _parse_row(line)
        if parsed is not None and parsed[0] == source_id:
            lines[i] = new_row + "\n"
            updated = True
            break

    if not updated:
        # Append after the last pipe row, or at the end of file.
        insert_at = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip().startswith("|"):
                insert_at = i + 1
                break
        lines.insert(insert_at, new_row + "\n")

    registry_path.write_text("".join(lines), encoding="utf-8")
    return RegistrationResult(ok=True)
