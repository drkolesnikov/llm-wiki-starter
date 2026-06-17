"""Command line interface for the LLM Wiki installer.

Subcommands live in the :mod:`llm_wiki_wizard.commands` package and are wired
in via directory-scan auto-discovery. Adding a command requires only dropping
a ``commands/<name>.py`` module exposing ``register(app)`` — no edit here.
"""

from __future__ import annotations

import typer

from .commands import register_all


app = typer.Typer(help="Spawn and inspect visible namespaced llm-wiki workspaces.")
register_all(app)


if __name__ == "__main__":
    app()
