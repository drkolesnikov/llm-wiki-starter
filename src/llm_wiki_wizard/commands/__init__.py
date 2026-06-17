"""Auto-discovered command modules for the LLM Wiki CLI.

Adding a subcommand requires only dropping a ``commands/<name>.py`` module
that exposes a module-level ``def register(app: typer.Typer) -> None``. The
loader below scans this package directory at import time and wires each module
into the Typer app, so neither ``cli.py`` nor this file needs editing for a
new command. Discovery is by directory scan, NOT a hand-maintained list.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import List, Tuple, Any

import typer

from llm_wiki_wizard._registry import discover_modules


def register_all(app: typer.Typer) -> None:
    """Discover sibling command modules and register each onto ``app``.

    Every module in this package that defines a callable ``register(app)`` is
    imported and invoked in deterministic (sorted) order. Modules whose names
    start with an underscore are skipped so private helpers can live alongside
    commands.
    """
    for _name, register in discover_modules(__path__, __name__, "register", sort=True):
        if callable(register):
            register(app)
