#!/usr/bin/env python3
"""Structural checks for the LLM wiki starter repository."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ALLOWED_ARTIFACT_TYPES = {
    "knowledge-note",
    "source-summary",
    "source-map",
    "source-registry",
    "index",
    "log",
    "workstream",
    "review",
    "decision",
    "agent-task",
    "source-ingest-policy",
}

ALLOWED_STATUSES = {
    "draft",
    "active",
    "needs-review",
    "verified",
    "conflicted",
    "deprecated",
}

ALLOWED_SOURCE_TIERS = {
    "primary",
    "secondary",
    "reference",
    "background",
    "restricted",
}

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if ".git" not in path.parts
    )


def split_frontmatter(text: str) -> tuple[dict[str, object], int] | tuple[None, int]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, 0
    for end_index in range(1, len(lines)):
        if lines[end_index].strip() == "---":
            return parse_frontmatter(lines[1:end_index]), end_index + 1
    return {}, len(lines)


def parse_frontmatter(lines: list[str]) -> dict[str, object]:
    data: dict[str, object] = {}
    current_key: str | None = None
    for raw_line in lines:
        if not raw_line.strip():
            continue
        if raw_line.startswith("  - ") and current_key:
            value = raw_line[4:].strip()
            current = data.setdefault(current_key, [])
            if isinstance(current, list):
                current.append(clean_scalar(value))
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if value == "[]":
            data[key] = []
        elif value:
            data[key] = clean_scalar(value)
        else:
            data[key] = []
    return data


def clean_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def should_require_frontmatter(path: Path) -> bool:
    if path.name == "README.md":
        return False
    if ".github" in path.parts:
        return False
    if "templates" in path.parts:
        return False
    rel_path = rel(path)
    return (
        rel_path.startswith("meta/")
        or rel_path.startswith("knowledge/")
        or rel_path.startswith("reviews/")
        or rel_path.startswith("projects/")
        or rel_path.startswith("raw/derived/")
        or rel_path == "docs/source-ingest-policy.md"
    )


def registered_sources() -> dict[str, dict[str, str]]:
    registry_path = ROOT / "meta" / "source-registry.md"
    if not registry_path.exists():
        return {}
    sources: dict[str, dict[str, str]] = {}
    for line in registry_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or cells[0] in {"Source ID", "---"} or set(cells[0]) == {"-"}:
            continue
        if len(cells) < 6:
            continue
        source_id, title, tier, status, derived_path, notes = cells[:6]
        if source_id and source_id != "-":
            sources[source_id] = {
                "title": title,
                "tier": tier,
                "status": status,
                "derived_path": derived_path,
                "notes": notes,
            }
    return sources


def source_values(frontmatter: dict[str, object]) -> list[str]:
    raw = frontmatter.get("sources")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    value = str(raw).strip()
    return [value] if value else []


def validate_frontmatter(errors: list[str], sources: dict[str, dict[str, str]]) -> None:
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        frontmatter, _ = split_frontmatter(text)
        if frontmatter is None:
            if should_require_frontmatter(path):
                errors.append(f"{rel(path)}: missing frontmatter")
            continue
        artifact_type = frontmatter.get("artifact_type")
        status = frontmatter.get("status")
        if artifact_type is not None and artifact_type not in ALLOWED_ARTIFACT_TYPES:
            errors.append(f"{rel(path)}: unknown artifact_type {artifact_type!r}")
        if status is not None and status not in ALLOWED_STATUSES:
            errors.append(f"{rel(path)}: unknown status {status!r}")
        source_tier = frontmatter.get("source_tier")
        if source_tier is not None and source_tier not in ALLOWED_SOURCE_TIERS:
            errors.append(f"{rel(path)}: unknown source_tier {source_tier!r}")
        if should_require_frontmatter(path):
            if artifact_type is None:
                errors.append(f"{rel(path)}: missing artifact_type")
            if status is None:
                errors.append(f"{rel(path)}: missing status")
        for source_id in source_values(frontmatter):
            if source_id not in sources:
                errors.append(f"{rel(path)}: source {source_id!r} is not registered")


def validate_registry(errors: list[str], sources: dict[str, dict[str, str]]) -> None:
    for source_id, row in sources.items():
        tier = row["tier"]
        status = row["status"]
        derived_path = row["derived_path"]
        if tier not in ALLOWED_SOURCE_TIERS:
            errors.append(f"meta/source-registry.md: source {source_id!r} has unknown tier {tier!r}")
        if status not in ALLOWED_STATUSES:
            errors.append(f"meta/source-registry.md: source {source_id!r} has unknown status {status!r}")
        if derived_path and derived_path != "-":
            target = (ROOT / derived_path).resolve()
            try:
                target.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"meta/source-registry.md: source {source_id!r} derived path leaves repository")
                continue
            if not target.exists():
                errors.append(f"meta/source-registry.md: source {source_id!r} derived path is missing: {derived_path}")


def validate_links(errors: list[str]) -> None:
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            href = match.group(1).strip()
            if should_skip_link(href):
                continue
            target_text = href.split("#", 1)[0]
            if not target_text:
                continue
            target = (path.parent / target_text).resolve()
            try:
                target.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"{rel(path)}: link leaves repository: {href}")
                continue
            if not target.exists():
                errors.append(f"{rel(path)}: broken link: {href}")


def should_skip_link(href: str) -> bool:
    lowered = href.lower()
    return (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("mailto:")
        or lowered.startswith("#")
        or lowered.startswith("tel:")
    )


def main() -> int:
    errors: list[str] = []
    sources = registered_sources()
    validate_frontmatter(errors, sources)
    validate_registry(errors, sources)
    validate_links(errors)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"\nRepository validation failed with {len(errors)} issue(s).")
        return 1
    print("Repository validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
