"""OKF v0.1 export for the LLM Wiki starter.

``export(wiki_root, out_dir) -> ExportResult`` renders the wiki as an OKF
bundle in *out_dir*, reusing index/log generation from ``tools/generate_indexes``.

Compatibility profile
---------------------
``OKF_V01_PROFILE`` is a named, versioned dict that owns all translation rules
targeting OKF v0.1.  It carries:

- ``version``           — profile identifier string.
- ``namespace``         — extension-key prefix for governance fields.
- ``type_map``          — verbatim: wiki ``artifact_type`` → OKF ``type``.
- ``governance_fields`` — fields written as extension keys under *namespace*.
- ``recommended_fields``— OKF recommended fields emitted only when present.

Translation rules
-----------------
1. ``artifact_type`` → OKF ``type`` verbatim.
2. Governance fields (``status``, ``tags``, ``sources``, ``source_count``,
   ``linked_reviews``, ``source_tier``, ``owner``, ``aliases``,
   ``linked_concepts``) → extension keys ``<namespace>:<field>``.
3. ``title`` → ``title``; ``description``/``resource`` → OKF recommended
   fields of the same name when present (omit when absent, never empty).
4. ``updated`` → ``updated`` verbatim.
5. ``[[wikilinks]]`` and ``linked_concepts`` entries resolved to relative
   Markdown links to the target concept's bundle path; unresolved targets
   left as plain text and reported in ``ExportResult.unresolved_links``.
6. Reserved ``index.md`` + ``log.md`` emitted by REUSING ``generate_indexes``.
7. Write only into *out_dir*; never mutate the wiki.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from wiki_spec import SKIP_DIRS
except ImportError:
    from tools.wiki_spec import SKIP_DIRS

try:
    from generate_indexes import generate as _generate_indexes
except ImportError:
    from tools.generate_indexes import generate as _generate_indexes

try:
    from frontmatter import parse_frontmatter
except ImportError:
    from tools.frontmatter import parse_frontmatter


# ---------------------------------------------------------------------------
# Compatibility profile
# ---------------------------------------------------------------------------

#: Versioned OKF v0.1 compatibility profile.  All translation rules live here.
OKF_V01_PROFILE: dict[str, Any] = {
    "version": "okf-v0.1",
    "namespace": "llm-wiki",
    # artifact_type is mapped verbatim; this exists for documentation clarity.
    "type_map": "verbatim",
    # Fields written as extension keys under ``<namespace>:<field>``.
    "governance_fields": [
        "status",
        "tags",
        "sources",
        "source_count",
        "linked_reviews",
        "source_tier",
        "owner",
        "aliases",
        "linked_concepts",
    ],
    # OKF recommended fields — emitted when present in source frontmatter,
    # omitted when absent; never written as empty strings.
    "recommended_fields": ["description", "resource"],
}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ExportResult:
    """Outcome of an :func:`export` call."""

    profile: str = ""                          # profile version used
    artifacts_exported: int = 0                # count of artifact files written
    unresolved_links: list[str] = field(default_factory=list)  # reported, not fatal
    index_written: bool = False
    log_written: bool = False

    def to_dict(self) -> dict:
        return {
            "profile": self.profile,
            "artifacts_exported": self.artifacts_exported,
            "unresolved_links": sorted(self.unresolved_links),
            "index_written": self.index_written,
            "log_written": self.log_written,
        }


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------

_WIKILINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")


def _render_frontmatter(fields: dict[str, Any]) -> str:
    """Render an OKF frontmatter block from *fields*."""
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
# Wikilink resolution
# ---------------------------------------------------------------------------


def _build_title_index(wiki_root: Path) -> dict[str, Path]:
    """Map lowercase titles/slugs → absolute artifact paths in *wiki_root*."""
    index: dict[str, Path] = {}
    for md_path in wiki_root.rglob("*.md"):
        if any(part in SKIP_DIRS for part in md_path.relative_to(wiki_root).parts):
            continue
        # slug from filename
        slug = md_path.stem.lower().replace("-", " ").replace("_", " ")
        index[slug] = md_path
        index[md_path.stem.lower()] = md_path
        # title from frontmatter if present
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = parse_frontmatter(text)
        title = str(fm.data.get("title", "") or "")
        if title:
            index[title.lower()] = md_path
        # aliases
        # (aliases are a list field; skip for now — slug + title coverage is sufficient)
    return index


def _resolve_wikilink(target: str, source_path: Path, title_index: dict[str, Path]) -> str | None:
    """Return a relative Markdown path for *target*, or None when unresolved."""
    lookup = target.lower().strip()
    resolved = title_index.get(lookup)
    if resolved is None:
        # Try slug form
        slug = lookup.replace(" ", "-")
        resolved = title_index.get(slug)
    if resolved is None:
        return None
    try:
        return resolved.relative_to(source_path.parent).as_posix()
    except ValueError:
        # Different branch of the tree — use relative path from common root
        # This should not occur within a single wiki, but handle gracefully
        return None


def _rewrite_wikilinks(
    body: str,
    source_path: Path,
    title_index: dict[str, Path],
    unresolved: list[str],
) -> str:
    """Replace ``[[target]]`` with ``[target](relative/path.md)`` or plain text."""

    def replacer(m: re.Match) -> str:
        target = m.group(1)
        rel = _resolve_wikilink(target, source_path, title_index)
        if rel is None:
            unresolved.append(f"{source_path.name}: [[{target}]]")
            return target  # plain text, no link
        return f"[{target}]({rel})"

    return _WIKILINK_RE.sub(replacer, body)


# ---------------------------------------------------------------------------
# Single-artifact export
# ---------------------------------------------------------------------------


def _export_artifact(
    src_path: Path,
    out_path: Path,
    wiki_root: Path,
    title_index: dict[str, Path],
    profile: dict[str, Any],
    result: ExportResult,
) -> None:
    """Translate one artifact from *src_path* to *out_path* using *profile*."""
    text = src_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text, preserve_raw=True)
    scalars = {k: str(v) for k, v in fm.data.items() if not isinstance(v, list)}
    body = fm.body

    namespace = profile["namespace"]
    governance_fields = profile["governance_fields"]
    recommended_fields = profile["recommended_fields"]

    okf_fields: dict[str, Any] = {}

    # 1. type (required): artifact_type verbatim
    artifact_type = scalars.get("artifact_type", "")
    if artifact_type:
        okf_fields["type"] = artifact_type

    # 2. title (recommended → required in OKF context)
    title = scalars.get("title", "")
    if title:
        okf_fields["title"] = title

    # 3. updated verbatim
    updated = scalars.get("updated", "")
    if updated:
        okf_fields["updated"] = updated

    # 4. Recommended fields: description, resource — only when present & non-empty
    for rf in recommended_fields:
        val = scalars.get(rf, "")
        if val:
            okf_fields[rf] = val

    # 5. Governance extension keys
    for gf in governance_fields:
        # List-valued governance fields
        if gf in ("tags", "sources", "linked_reviews", "aliases", "linked_concepts"):
            raw_val = fm.data.get(gf)
            items: list[str] = list(raw_val) if isinstance(raw_val, list) else (
                [str(raw_val)] if raw_val else []
            )
            if items:
                # Resolve linked_concepts entries to relative links
                if gf == "linked_concepts":
                    resolved_items = []
                    for item in items:
                        rel = _resolve_wikilink(item, out_path, title_index)
                        if rel is None:
                            result.unresolved_links.append(f"{src_path.name}: linked_concepts: {item}")
                            resolved_items.append(item)  # plain text
                        else:
                            resolved_items.append(f"[{item}]({rel})")
                    okf_fields[f"{namespace}:{gf}"] = resolved_items
                else:
                    okf_fields[f"{namespace}:{gf}"] = items
        else:
            # Scalar governance field
            val = scalars.get(gf, "")
            if gf == "source_count" and not val:
                # try integer representation
                pass
            if val:
                okf_fields[f"{namespace}:{gf}"] = val

    # Rewrite wikilinks in the body; errors are non-fatal and reported
    body = _rewrite_wikilinks(body, out_path, title_index, result.unresolved_links)

    # Render output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fm_str = _render_frontmatter(okf_fields)
    out_path.write_text(fm_str + "\n" + body, encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export(wiki_root: Path | str, out_dir: Path | str) -> ExportResult:
    """Export the wiki at *wiki_root* as an OKF v0.1 bundle into *out_dir*.

    Parameters
    ----------
    wiki_root:
        Root directory of the source wiki.  Must contain ``meta/``.
    out_dir:
        Destination directory for the OKF bundle.  Created if it does not
        exist.  Existing contents are overwritten.  The source wiki is
        **never** mutated.

    Returns
    -------
    ExportResult
        Counts, notable events, and resolved/unresolved link report.
    """
    wiki_root = Path(wiki_root).resolve()
    out_dir = Path(out_dir).resolve()

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    result = ExportResult(profile=OKF_V01_PROFILE["version"])
    profile = OKF_V01_PROFILE

    # Build a title → path index over the SOURCE wiki for link resolution.
    # We map to out_dir paths after copying structure so that relative links
    # inside the bundle point to the correct bundle paths.
    title_index_src = _build_title_index(wiki_root)
    # Remap index values from wiki_root paths to out_dir paths
    title_index: dict[str, Path] = {}
    for key, src_path in title_index_src.items():
        try:
            rel = src_path.relative_to(wiki_root)
        except ValueError:
            continue
        title_index[key] = out_dir / rel

    # Walk all governed Markdown files and translate each one.
    for md_path in sorted(wiki_root.rglob("*.md")):
        if any(part in SKIP_DIRS for part in md_path.relative_to(wiki_root).parts):
            continue
        rel = md_path.relative_to(wiki_root)
        out_path = out_dir / rel
        _export_artifact(md_path, out_path, wiki_root, title_index, profile, result)
        result.artifacts_exported += 1

    # Emit reserved index.md + log.md by reusing generate_indexes.
    # generate() writes into out_dir — that satisfies build-output discipline.
    gen = _generate_indexes(out_dir)
    result.index_written = bool(gen.written or gen.unchanged)  # True if any index produced
    # log.md is written when indexes changed; also check if it already exists
    log_path = out_dir / "meta" / "log.md"
    result.log_written = log_path.exists()

    return result
