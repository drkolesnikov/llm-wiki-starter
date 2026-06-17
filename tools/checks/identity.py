#!/usr/bin/env python3
"""Structural check: identity consistency for trust-bearing surfaces.

Verifies that the two canonical trust surfaces — README.md and the Codex
plugin metadata — only reference the canonical GitHub home for this
repository.  Any ``<owner>/llm-wiki-starter`` reference whose owner differs
from ``drkolesnikov`` is reported as an error.

Discovery: this module is auto-discovered by :func:`tools.checks.discover_checks`
because it lives in the ``tools/checks/`` package and exposes a ``check``
callable.  No edit to ``validate_repo.py`` is needed.

Scope: repo-specific guard — NOT vendored into the installer template tree.
"""

from __future__ import annotations

import re
from pathlib import Path

# The one canonical GitHub home for this repository.
CANONICAL_HOME: str = "drkolesnikov/llm-wiki-starter"

# Pattern: any GitHub-style <owner>/llm-wiki-starter slug embedded in text.
# We capture the owner part so we can compare it to the canonical one.
_SLUG_RE = re.compile(r"([A-Za-z0-9._-]+)/llm-wiki-starter")

# The two trust surfaces that must only reference the canonical owner.
_SURFACES = (
    "README.md",
    "plugins/llm-wiki/.codex-plugin/plugin.json",
)


def check(model, errors) -> None:  # noqa: ANN001
    """Fail if any trust surface references a non-canonical owner slug.

    ``model`` is a :class:`tools.wiki_model.RepoModel` (frozen dataclass) whose
    ``root`` attribute is the repository root :class:`~pathlib.Path`.
    ``errors`` is a mutable list; append a human-readable string per problem.
    """
    root: Path = model.root
    canonical_owner = CANONICAL_HOME.split("/")[0]

    for rel_path in _SURFACES:
        surface = root / rel_path
        if not surface.exists():
            continue  # missing surface is not this check's concern
        text = surface.read_text(encoding="utf-8")
        for match in _SLUG_RE.finditer(text):
            owner = match.group(1)
            if owner != canonical_owner:
                offending = match.group(0)
                errors.append(
                    f"identity: {rel_path}: found '{offending}' — "
                    f"expected canonical home '{CANONICAL_HOME}'"
                )
