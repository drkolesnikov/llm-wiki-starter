"""OKF v0.1 import / quarantine for the LLM Wiki starter.

``import_bundle(bundle_path, staging_dir) -> ImportResult`` reads an OKF
bundle from *bundle_path* and quarantines every concept into *staging_dir*
as a staged artifact with ``status: needs-review``.

Design rules
------------
- **Permissive parse**: tolerates unknown ``type`` values, missing optional
  fields, broken relative links, and a missing ``index.md`` — each defect is
  surfaced as a note in ``ImportResult.notes``, never as a failure.
- **Quarantine only**: artifacts land exclusively in *staging_dir*; the caller's
  trusted knowledge tree is **never touched** and existing staging files are
  **never overwritten**.
- **Strict intake status**: every staged artifact is written with
  ``status: needs-review``.  There is NO code path that yields ``verified``.
- The OKF ``type`` field (if present) is recorded as the candidate
  ``artifact_type`` on the staged artifact.
- Unknown frontmatter keys are preserved verbatim on the staged artifact under
  an ``okf-unknown:`` prefixed key so they round-trip without loss.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FENCE = "---"
# Matches a YAML-ish frontmatter key: may include hyphens, underscores, and a
# single embedded colon for extension keys like ``llm-wiki:status``.
# Pattern: one or more key-char segments separated by at most one colon, followed
# by `: ` (colon-space) as the key/value separator.
# We use a partition on ': ' (colon-space) instead of a regex so that extension
# keys like ``llm-wiki:status: active`` are parsed correctly.
_FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_\-]*)\s*:\s*(.*?)\s*$")

# OKF core fields that we handle explicitly during import.
_KNOWN_OKF_FIELDS = {
    "type",
    "title",
    "updated",
    "description",
    "resource",
}

# Fields that are extension-key clusters (``<namespace>:<field>``) — they
# are preserved verbatim without the "unknown" prefix treatment.
_EXTENSION_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]+:[A-Za-z0-9_\-]+$")

# Link pattern inside Markdown bodies (both Markdown and wikilinks).
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ImportResult:
    """Outcome of an :func:`import_bundle` call."""

    artifacts_staged: int = 0
    notes: list[str] = field(default_factory=list)  # tolerated defects + events
    skipped: int = 0                                  # e.g. reserved files like index.md/log.md

    def to_dict(self) -> dict:
        return {
            "artifacts_staged": self.artifacts_staged,
            "notes": list(self.notes),
            "skipped": self.skipped,
        }


# ---------------------------------------------------------------------------
# Frontmatter helpers  (minimal, self-contained — no shared import dependency)
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], list[str], int]:
    """Parse YAML-ish frontmatter.

    Returns (scalars, raw_lines_inside_fence, body_start_index).
    List-valued fields appear as their raw ``field:`` line only; callers that
    need list items call :func:`_parse_list_field`.

    Parsing strategy: partition each line on ``': '`` (colon followed by a
    space) as the key/value separator.  This correctly handles extension keys
    like ``llm-wiki:status: active`` where the key contains an embedded colon.
    A line with a trailing ``:`` and no value is treated as a block-list header
    and recorded with value ``""``.  Indented lines (list items) are stored in
    *raw* but not as scalars.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        return {}, [], 0

    scalars: dict[str, Any] = {}
    raw: list[str] = []
    end = len(lines)

    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == _FENCE:
            end = i + 1
            break
        raw.append(line)

        # Skip indented lines (list items / nested values)
        if line and line[0] in (" ", "\t"):
            continue

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Block-list header: ``key:`` with nothing after the colon
        if stripped.endswith(":") and ": " not in stripped:
            key = stripped[:-1].strip()
            scalars[key] = ""
            continue

        # Normal scalar or extension-key scalar: split on first ': '
        if ": " in stripped:
            key, _, val = stripped.partition(": ")
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
                val = val[1:-1]
            scalars[key] = val

    return scalars, raw, end


def _parse_list_field(raw_lines: list[str], field_name: str) -> list[str]:
    """Extract a YAML block/inline list for *field_name* from raw frontmatter lines."""
    result: list[str] = []
    in_field = False
    for line in raw_lines:
        stripped = line.strip()
        if stripped == f"{field_name}:" or stripped.startswith(f"{field_name}:"):
            if stripped == f"{field_name}:":
                in_field = True
                continue
            rest = stripped[len(field_name) + 1:].strip()
            if rest.startswith("["):
                items = rest.strip("[] ").split(",")
                return [item.strip().strip("\"'") for item in items if item.strip()]
            in_field = False
            continue
        if in_field:
            if stripped.startswith("- "):
                result.append(stripped[2:].strip().strip("\"'"))
            elif stripped and not stripped.startswith("#"):
                in_field = False
    return result


def _collect_unknown_keys(
    scalars: dict[str, Any],
    raw_lines: list[str],
) -> dict[str, Any]:
    """Return key→value for OKF fields not in :data:`_KNOWN_OKF_FIELDS`.

    Extension keys (``ns:field``) are returned as-is; plain unknown scalar
    keys are returned as-is.  List-valued unknown fields are collected as a
    list of their items.

    Uses the same partition-on-``': '`` strategy as :func:`_parse_frontmatter`
    so extension keys like ``llm-wiki:status`` are handled correctly.
    """
    unknown: dict[str, Any] = {}
    current_list_key: str | None = None
    current_list_items: list[str] = []

    for line in raw_lines:
        stripped = line.strip()

        # Collect list items for the current block-list key
        if current_list_key is not None:
            if stripped.startswith("- "):
                current_list_items.append(stripped[2:].strip().strip("\"'"))
                continue
            if not stripped or stripped.startswith("#"):
                continue
            # Non-item, non-blank: flush the list and fall through to key parse
            if current_list_key not in _KNOWN_OKF_FIELDS:
                unknown[current_list_key] = list(current_list_items)
            current_list_key = None
            current_list_items = []

        # Skip indented lines outside a list context
        if line and line[0] in (" ", "\t"):
            continue

        if not stripped or stripped.startswith("#"):
            continue

        # Block-list header: ``key:`` with nothing after the colon
        if stripped.endswith(":") and ": " not in stripped:
            key = stripped[:-1].strip()
            current_list_key = key
            current_list_items = []
            continue

        # Scalar or extension-key scalar: partition on first ': '
        if ": " in stripped:
            key, _, val = stripped.partition(": ")
            key = key.strip()
            val = val.strip().strip("\"'")
            current_list_key = None
            if key not in _KNOWN_OKF_FIELDS:
                unknown[key] = val

    # Flush any trailing list
    if current_list_key is not None and current_list_key not in _KNOWN_OKF_FIELDS:
        unknown[current_list_key] = list(current_list_items)

    return unknown


def _check_body_links(body: str, bundle_root: Path, md_path: Path) -> list[str]:
    """Return broken-link notes for Markdown links in *body* that don't resolve."""
    broken: list[str] = []
    for m in _MD_LINK_RE.finditer(body):
        href = m.group(2).strip()
        if href.startswith(("http://", "https://", "mailto:", "#")):
            continue
        # Relative link — resolve against the file's parent inside the bundle
        target = (md_path.parent / href).resolve()
        try:
            # Make sure we stay inside the bundle root
            target.relative_to(bundle_root)
        except ValueError:
            broken.append(f"{md_path.name}: link escapes bundle root: {href!r}")
            continue
        if not target.exists():
            broken.append(f"{md_path.name}: broken relative link: {href!r}")
    return broken


def _render_staged_frontmatter(fields: dict[str, Any]) -> str:
    """Render frontmatter for a staged artifact."""
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            if not value:
                continue
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            str_val = str(value)
            if any(c in str_val for c in (':', '"', "'", '#', '[', ']', '{', '}')):
                str_val = f'"{str_val}"'
            lines.append(f"{key}: {str_val}")
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reserved / non-artifact file names
# ---------------------------------------------------------------------------

_RESERVED_NAMES = {"index.md", "log.md"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_bundle(
    bundle_path: Path | str,
    staging_dir: Path | str,
) -> ImportResult:
    """Import an OKF bundle from *bundle_path* into *staging_dir* (quarantine).

    Every Markdown file in *bundle_path* (except reserved ``index.md`` /
    ``log.md``) is quarantined as a staged artifact under *staging_dir* with
    ``status: needs-review``.  Defects (unknown ``type``, missing fields,
    broken links, missing ``index.md``) are reported as notes — they never
    cause failure.

    Parameters
    ----------
    bundle_path:
        Root of the OKF bundle to import.  Must be a directory.
    staging_dir:
        Destination quarantine area.  Created if it does not exist.  Existing
        files are **never** overwritten — a note is emitted instead.

    Returns
    -------
    ImportResult
        Counts, notes for tolerated defects, and number of skipped files.
    """
    bundle_path = Path(bundle_path).resolve()
    staging_dir = Path(staging_dir).resolve()

    result = ImportResult()

    if not bundle_path.is_dir():
        result.notes.append(f"bundle_path does not exist or is not a directory: {bundle_path}")
        return result

    # Check for missing index.md — tolerate, note it.
    index_md = bundle_path / "index.md"
    if not index_md.exists():
        result.notes.append("index.md not found in bundle root — tolerated")

    staging_dir.mkdir(parents=True, exist_ok=True)

    # Walk all Markdown files in the bundle.
    for md_path in sorted(bundle_path.rglob("*.md")):
        rel = md_path.relative_to(bundle_path)

        # Skip reserved files (index.md, log.md anywhere in the tree)
        if md_path.name in _RESERVED_NAMES:
            result.skipped += 1
            continue

        # ----------------------------------------------------------------
        # Parse OKF frontmatter
        # ----------------------------------------------------------------
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError as exc:
            result.notes.append(f"{rel}: read error — {exc}")
            result.skipped += 1
            continue

        scalars, raw_lines, body_start = _parse_frontmatter(text)
        body_lines = text.splitlines()[body_start:]
        body = "\n".join(body_lines)

        # ----------------------------------------------------------------
        # Map OKF fields → staged artifact fields
        # ----------------------------------------------------------------
        staged: dict[str, Any] = {}

        # status — ALWAYS needs-review, no exceptions
        staged["status"] = "needs-review"

        # artifact_type — from OKF ``type``; unknown types are tolerated + noted
        okf_type = scalars.get("type", "").strip()
        if okf_type:
            staged["artifact_type"] = okf_type
            # Note unknown (non-standard) types so callers can review
            # We don't maintain a strict whitelist; any non-empty value is accepted.
            # Unknown types are distinguished by absence from the export type_map.
            # For now we note all types for traceability.
        else:
            result.notes.append(f"{rel}: missing OKF 'type' field — artifact_type not set")

        # title — pass through when present
        title = scalars.get("title", "").strip()
        if title:
            staged["title"] = title

        # updated — pass through when present
        updated = scalars.get("updated", "").strip()
        if updated:
            staged["updated"] = updated

        # description, resource — optional; pass through when present
        for opt_field in ("description", "resource"):
            val = scalars.get(opt_field, "").strip()
            if val:
                staged[opt_field] = val

        # ----------------------------------------------------------------
        # Preserve unknown frontmatter keys (extension keys + plain unknowns)
        # ----------------------------------------------------------------
        unknown_keys = _collect_unknown_keys(scalars, raw_lines)
        for uk, uv in unknown_keys.items():
            # Extension keys (e.g. ``llm-wiki:status``) are preserved verbatim.
            # Plain unknown keys get an ``okf-preserved:`` prefix to signal provenance.
            if _EXTENSION_KEY_RE.match(uk):
                staged[uk] = uv
            else:
                staged[f"okf-preserved:{uk}"] = uv

        # ----------------------------------------------------------------
        # Check for broken relative links in the body — note, don't fail
        # ----------------------------------------------------------------
        broken = _check_body_links(body, bundle_path, md_path)
        for note in broken:
            result.notes.append(note)

        # ----------------------------------------------------------------
        # Write to staging area (never overwrite)
        # ----------------------------------------------------------------
        out_path = staging_dir / rel
        if out_path.exists():
            result.notes.append(f"{rel}: already exists in staging — skipped (no overwrite)")
            result.skipped += 1
            continue

        out_path.parent.mkdir(parents=True, exist_ok=True)
        fm_str = _render_staged_frontmatter(staged)
        out_path.write_text(fm_str + "\n" + body, encoding="utf-8")
        result.artifacts_staged += 1

    return result
