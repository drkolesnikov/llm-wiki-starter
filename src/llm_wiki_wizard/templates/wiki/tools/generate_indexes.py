#!/usr/bin/env python3
"""Index generation for the LLM wiki starter repository.

``generate(root, dry_run=False) -> GenResult`` walks governed directories
(respecting SKIP_DIRS) and renders a per-directory ``index.md`` listing each
artifact's title + one-line description (when present) + status, with
repository-relative child-directory links for progressive disclosure.

Meta contract
-------------
- ``meta/index.md`` is regenerated as part of the normal run.
- On a run with ≥1 index change, exactly one dated structured entry is appended
  to ``meta/log.md``; a no-op run appends nothing; prior history is never
  rewritten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

try:  # script invocation: ``tools/`` is on sys.path[0]
    from wiki_spec import SKIP_DIRS
except ImportError:  # imported as ``tools.generate_indexes``
    from tools.wiki_spec import SKIP_DIRS


# ---------------------------------------------------------------------------
# Frontmatter helpers (self-contained; no dependency on validate_repo so this
# file can be copied to vendored templates without pulling in extra imports)
# ---------------------------------------------------------------------------

_FENCE = "---"
_FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _clean(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Return a flat dict of scalar frontmatter fields; ignore list items."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == _FENCE:
            break
        m = _FIELD_RE.match(line)
        if m:
            result[m.group(1)] = _clean(m.group(2))
    return result


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class GenResult:
    """Outcome of a ``generate()`` call."""

    written: set[str] = field(default_factory=set)       # relative POSIX paths
    unchanged: set[str] = field(default_factory=set)     # relative POSIX paths
    log_appended: bool = False
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "written": sorted(self.written),
            "unchanged": sorted(self.unchanged),
            "log_appended": self.log_appended,
            "dry_run": self.dry_run,
        }


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------


def _collect_artifacts(directory: Path, root: Path) -> list[dict]:
    """Return parsed info for governed Markdown files directly inside *directory*.

    Excludes ``index.md`` itself, README.md, and any file whose parent parts
    contain a SKIP_DIR name.  Returns a stable (alphabetical-by-path) list of
    dicts with keys: path, title, description, status.
    """
    artifacts = []
    for md_path in sorted(directory.glob("*.md")):
        if md_path.name.lower() in {"index.md", "readme.md"}:
            continue
        if any(part in SKIP_DIRS for part in md_path.relative_to(root).parts):
            continue
        text = md_path.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        # Must have at least a recognisable artifact identity
        artifact_type = fm.get("artifact_type", "")
        title = fm.get("title", "")
        if not artifact_type and not title:
            # Infer a title from the H1 heading if there is one
            for line in text.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
        if not title:
            title = md_path.stem.replace("-", " ").replace("_", " ").title()
        artifacts.append(
            {
                "path": md_path,
                "title": title,
                "description": fm.get("description", ""),
                "status": fm.get("status", ""),
            }
        )
    return artifacts


def _child_dirs(directory: Path, root: Path) -> list[Path]:
    """Return immediate sub-directories that are not in SKIP_DIRS."""
    result = []
    for child in sorted(directory.iterdir()):
        if not child.is_dir():
            continue
        if child.name in SKIP_DIRS:
            continue
        result.append(child)
    return result


def _render_index(directory: Path, root: Path, today: str) -> str:
    """Render the index.md content for *directory*."""
    dir_title = directory.name.replace("-", " ").replace("_", " ").title()
    lines: list[str] = [
        "---",
        "artifact_type: index",
        "status: active",
        f"updated: {today}",
        "---",
        "",
        f"# {dir_title} Index",
        "",
    ]

    artifacts = _collect_artifacts(directory, root)
    if artifacts:
        lines.append("## Artifacts")
        lines.append("")
        for art in artifacts:
            rel_path = art["path"].relative_to(directory).as_posix()
            status_tag = f" `[{art['status']}]`" if art["status"] else ""
            if art["description"]:
                lines.append(f"- [{art['title']}]({rel_path}){status_tag} — {art['description']}")
            else:
                lines.append(f"- [{art['title']}]({rel_path}){status_tag}")
        lines.append("")

    child_dirs = _child_dirs(directory, root)
    if child_dirs:
        lines.append("## Sub-directories")
        lines.append("")
        for child in child_dirs:
            rel_child = (child / "index.md").relative_to(directory).as_posix()
            child_label = child.name.replace("-", " ").replace("_", " ").title()
            lines.append(f"- [{child_label}]({rel_child})")
        lines.append("")

    return "\n".join(lines)


def _write_if_changed(path: Path, content: str, dry_run: bool) -> bool:
    """Write *content* to *path* iff it differs from the existing file.

    Returns True if the file was (or would be) written.
    """
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == content:
            return False  # byte-identical — idempotent
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return True


def _governed_dirs(root: Path) -> list[Path]:
    """Return all directories under *root* that should receive an index.md.

    Only directories that contain at least one non-index Markdown artifact OR
    at least one governed sub-directory are included. Tool/cache dirs are
    excluded by SKIP_DIRS.
    """
    governed = []
    for dirpath in sorted(root.rglob("*")):
        if not dirpath.is_dir():
            continue
        if any(part in SKIP_DIRS for part in dirpath.relative_to(root).parts):
            continue
        # Check for any .md files (excluding index.md/README.md) or governed sub-dirs
        has_md = any(
            p.name.lower() not in {"index.md", "readme.md"}
            for p in dirpath.glob("*.md")
        )
        has_children = any(
            c.is_dir() and c.name not in SKIP_DIRS
            for c in dirpath.iterdir()
        )
        if has_md or has_children:
            governed.append(dirpath)
    return governed


def _append_log(log_path: Path, today: str, written: set[str], dry_run: bool) -> bool:
    """Append exactly one dated log entry to *log_path* describing the changes.

    Returns True if an entry was (or would be) appended. Never rewrites history.
    """
    entry_lines = [
        f"## {today}",
        "",
        f"- Regenerated {len(written)} index(es): {', '.join(sorted(written))}.",
        "",
    ]
    entry = "\n".join(entry_lines)

    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
    else:
        # Bootstrap a minimal log file
        existing = "\n".join(
            [
                "---",
                "artifact_type: log",
                "status: active",
                "updated: " + today,
                "---",
                "",
                "# Maintenance Log",
                "",
            ]
        )

    # Idempotence: if today's heading already appears, do not append again
    if f"## {today}" in existing:
        return False

    new_content = existing.rstrip("\n") + "\n\n" + entry
    if not dry_run:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(new_content, encoding="utf-8")
    return True


def generate(root: Path | str, *, dry_run: bool = False) -> GenResult:
    """Generate ``index.md`` files throughout the governed wiki tree.

    Parameters
    ----------
    root:
        Path to the wiki root (the directory that contains ``meta/``, ``docs/``,
        ``tools/``, etc.).
    dry_run:
        When True, compute what would change but write nothing.

    Returns
    -------
    GenResult
        Sets of relative POSIX paths written/unchanged, plus log_appended flag.
    """
    root = Path(root).resolve()
    today = date.today().isoformat()
    result = GenResult(dry_run=dry_run)

    meta_dir = root / "meta"

    # Walk every governed directory and render a per-directory index.
    # meta/ is excluded here — its index.md is the top-level wiki index,
    # rendered separately below with a different template.
    for directory in _governed_dirs(root):
        if directory == meta_dir:
            continue
        index_path = directory / "index.md"
        content = _render_index(directory, root, today)
        changed = _write_if_changed(index_path, content, dry_run)
        rel_path = index_path.relative_to(root).as_posix()
        if changed:
            result.written.add(rel_path)
        else:
            result.unchanged.add(rel_path)

    # Regenerate meta/index.md as the top-level wiki map.
    meta_index = meta_dir / "index.md"
    meta_content = _render_meta_index(root, today)
    changed = _write_if_changed(meta_index, meta_content, dry_run)
    rel_path = meta_index.relative_to(root).as_posix()
    if changed:
        result.written.add(rel_path)
    else:
        result.unchanged.add(rel_path)

    # Append log entry if anything changed
    if result.written:
        log_path = root / "meta" / "log.md"
        result.log_appended = _append_log(log_path, today, result.written, dry_run)

    return result


def _render_meta_index(root: Path, today: str) -> str:
    """Render a top-level meta/index.md that links to all governed directories."""
    meta_dir = root / "meta"
    lines: list[str] = [
        "---",
        "artifact_type: index",
        "status: active",
        f"updated: {today}",
        "---",
        "",
        "# Wiki Index",
        "",
        "## Directories",
        "",
    ]
    for dirpath in _governed_dirs(root):
        # Compute path to dirpath/index.md relative to meta/ using relative path math
        try:
            rel_index = (dirpath / "index.md").relative_to(meta_dir).as_posix()
        except ValueError:
            # Directory is outside meta/ — use root-relative path with proper up-navigation
            # Count depth of meta/ from root (it is always root/meta, so depth=1)
            up = "../"
            rel_from_root = dirpath.relative_to(root).as_posix()
            rel_index = up + rel_from_root + "/index.md"
        label = dirpath.relative_to(root).as_posix().replace("/", " / ").replace("-", " ").replace("_", " ").title()
        lines.append(f"- [{label}]({rel_index})")
    lines.append("")
    lines.append("## Log")
    lines.append("")
    lines.append("- [Maintenance Log](log.md)")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Generate wiki index files.")
    parser.add_argument("root", nargs="?", default=".", help="Wiki root (default: .)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing.")
    parser.add_argument("--json", action="store_true", dest="json_out", help="JSON output.")
    args = parser.parse_args()

    result = generate(args.root, dry_run=args.dry_run)
    if args.json_out:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"Written: {len(result.written)}, Unchanged: {len(result.unchanged)}, Log appended: {result.log_appended}")
