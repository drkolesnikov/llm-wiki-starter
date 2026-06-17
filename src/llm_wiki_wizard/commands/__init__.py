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

import typer


def register_all(app: typer.Typer) -> None:
    """Discover sibling command modules and register each onto ``app``.

    Every module in this package that defines a callable ``register(app)`` is
    imported and invoked. Modules whose names start with an underscore are
    skipped so private helpers can live alongside commands.
    """
    for module_info in pkgutil.iter_modules(__path__):
        name = module_info.name
        if name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{name}")
        register = getattr(module, "register", None)
        if callable(register):
            register(app)
