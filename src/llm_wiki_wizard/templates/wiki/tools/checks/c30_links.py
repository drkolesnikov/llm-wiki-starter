#!/usr/bin/env python3
"""Structural check: standard Markdown links resolve inside the repository.

Wraps :func:`validate_repo.validate_links`. Ordered last among today's checks
(``c30``) to preserve the historical error-emission order.
"""

from __future__ import annotations

try:  # script invocation: ``tools/`` is on sys.path[0]
    import validate_repo
except ImportError:  # imported as ``tools.checks.c30_links``
    from tools import validate_repo


def check(model, errors) -> None:
    validate_repo.validate_links(errors)
