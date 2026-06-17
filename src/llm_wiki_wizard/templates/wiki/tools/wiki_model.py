#!/usr/bin/env python3
"""Parsed-repo model for the LLM wiki starter repository.

``load_repo_model`` parses every tracked Markdown artifact once into a
structured :class:`RepoModel`, reusing the validator's frontmatter and
source-registry parsing so downstream checks share a single seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:  # script invocation: ``tools/`` is on sys.path[0]
    from frontmatter import markdown_files, split_frontmatter
except ImportError:  # imported as ``tools.wiki_model``
    from tools.frontmatter import markdown_files, split_frontmatter

try:
    from validate_repo import registered_sources
except ImportError:
    from tools.validate_repo import registered_sources


@dataclass(frozen=True)
class Artifact:
    """A single Markdown artifact and its parsed frontmatter/body."""

    path: Path
    frontmatter: dict[str, object]
    body: str


@dataclass(frozen=True)
class RepoModel:
    """Parsed view of the repository: artifacts plus registered sources."""

    root: Path
    artifacts: list[Artifact] = field(default_factory=list)
    sources: dict[str, dict[str, str]] = field(default_factory=dict)


def load_repo_model(root: Path) -> RepoModel:
    """Parse all Markdown artifacts under ``root`` into a :class:`RepoModel`.

    Each artifact carries its ``path``, parsed ``frontmatter`` dict (empty when
    a document has no frontmatter), and the remaining ``body`` text. Registered
    sources are read from ``meta/source-registry.md`` via the shared parser.
    """

    root = Path(root)
    artifacts: list[Artifact] = []
    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8")
        fm, body_start = split_frontmatter(text)
        body_lines = text.splitlines()[body_start:]
        body = "\n".join(body_lines)
        artifacts.append(
            Artifact(
                path=path,
                frontmatter=fm if fm is not None else {},
                body=body,
            )
        )
    return RepoModel(root=root, artifacts=artifacts, sources=registered_sources(root))
