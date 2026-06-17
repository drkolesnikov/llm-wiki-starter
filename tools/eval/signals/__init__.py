#!/usr/bin/env python3
"""Auto-discovered evaluation signals.

Each module in this package exposes a module-level ``SIGNAL`` object that
satisfies the :class:`tools.eval.Signal` protocol::

    from tools.eval import Finding

    class _MySignal:
        id = "my-signal"
        finding_class = "deterministic"

        def run(self, model):
            return [Finding(self.id, self.finding_class, "info", [], "…")]

    SIGNAL = _MySignal()

The suite discovers every sibling module here and runs each module's ``SIGNAL``
in **sorted filename order**, so report and finding text stay deterministic.
Adding a signal is therefore add-a-file: drop a ``*.py`` module exposing
``SIGNAL`` into this directory; no edit to :mod:`tools.eval` is required.

Modules whose names start with ``_`` are treated as private helpers and are
skipped by discovery. This package ships empty: the eight signal slices land as
separate add-a-file modules under issue #20.
"""

from __future__ import annotations
