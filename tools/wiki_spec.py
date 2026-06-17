#!/usr/bin/env python3
"""Shared structural specification for the LLM wiki starter repository.

This module is the single source of truth for the validator's allow-lists,
skip directories, and the per-artifact required sections derived from the
templates under ``docs/templates/``.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".cache",
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "scratch",
    "tmp",
    "venv",
}

ALLOWED_ARTIFACT_TYPES = {
    "knowledge-note",
    "source-summary",
    "source-map",
    "source-registry",
    "index",
    "log",
    "milestone",
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

TEMPLATES_DIR = ROOT / "docs" / "templates"

_FRONTMATTER_FENCE = "---"
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")


def _template_artifact_type(text: str) -> str | None:
    """Return the ``artifact_type`` declared in a template's frontmatter."""

    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return None
    for line in lines[1:]:
        if line.strip() == _FRONTMATTER_FENCE:
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() == "artifact_type":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            return value or None
    return None


def _template_sections(text: str) -> list[str]:
    """Return the top-level ``##`` headings found in a template body."""

    sections: list[str] = []
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            sections.append(match.group(1).strip())
    return sections


def _build_required_sections(templates_dir: Path) -> dict[str, list[str]]:
    """Map each artifact_type to the ``##`` headings of its template.

    Artifact types with no template map to an empty list. When several
    templates declare the same artifact_type, the first encountered (sorted
    by file name) provides the canonical section list.
    """

    required: dict[str, list[str]] = {artifact: [] for artifact in ALLOWED_ARTIFACT_TYPES}
    if not templates_dir.is_dir():
        return required
    for template_path in sorted(templates_dir.glob("*.md")):
        text = template_path.read_text(encoding="utf-8")
        artifact_type = _template_artifact_type(text)
        if artifact_type is None or artifact_type not in required:
            continue
        if required[artifact_type]:
            continue
        required[artifact_type] = _template_sections(text)
    return required


REQUIRED_SECTIONS: dict[str, list[str]] = _build_required_sections(TEMPLATES_DIR)
