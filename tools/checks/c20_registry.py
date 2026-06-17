#!/usr/bin/env python3
"""Structural check: source-registry rows are well-formed.

Wraps :func:`validate_repo.validate_registry`. Ordered after the frontmatter
check (``c20`` > ``c10``) so error text matches today's emission order.
"""

from __future__ import annotations

try:  # script invocation: ``tools/`` is on sys.path[0]
    import validate_repo
except ImportError:  # imported as ``tools.checks.c20_registry``
    from tools import validate_repo


def check(model, errors) -> None:
    validate_repo.validate_registry(errors, model.sources)
