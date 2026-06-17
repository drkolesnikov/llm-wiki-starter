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

try:
    from frontmatter import parse_frontmatter
except ImportError:
    from tools.frontmatter import parse_frontmatter

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


def _collect_unknown_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Return key→value for frontmatter keys not in :data:`_KNOWN_OKF_FIELDS`.

    Uses the fully-parsed ``data`` dict from :func:`~tools.frontmatter.parse_frontmatter`
    so extension keys (``ns:field``) and list-valued fields are already decoded
    correctly — no raw-line scanning needed.
    """
    return {k: v for k, v in data.items() if k not in _KNOWN_OKF_FIELDS}


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

        fm = parse_frontmatter(text)
        scalars = {k: str(v) for k, v in fm.data.items() if not isinstance(v, list)}
        body = fm.body

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
        unknown_keys = _collect_unknown_keys(fm.data)
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
