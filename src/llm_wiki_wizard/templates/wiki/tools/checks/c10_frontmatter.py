#!/usr/bin/env python3
"""Structural check: frontmatter presence and allowed values.

Wraps :func:`validate_repo.validate_frontmatter` so the canonical logic lives
in one place and continues to honour a monkeypatched ``validate_repo.ROOT``.
The sort-ordering prefix (``c10``) fixes this check's position in the
deterministic discovery order ahead of registry/link checks.
"""

from __future__ import annotations

try:  # script invocation: ``tools/`` is on sys.path[0]
    import validate_repo
except ImportError:  # imported as ``tools.checks.c10_frontmatter``
    from tools import validate_repo


def check(model, errors) -> None:
    validate_repo.validate_frontmatter(errors, model.sources)
