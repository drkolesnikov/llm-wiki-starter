"""``index`` command (alias ``reindex``): generate wiki index files."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def register(app: typer.Typer) -> None:
    @app.command(name="index")
    def index(
        target: Path = typer.Argument(Path("."), help="Wiki root directory."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Generate index.md files throughout the wiki tree."""
        try:
            from tools.generate_indexes import generate
        except ImportError:
            # When running from inside an installed wiki the tools dir is local
            import sys as _sys
            _sys.path.insert(0, str(target / "tools"))
            from generate_indexes import generate  # type: ignore[no-redef]

        result = generate(target, dry_run=dry_run)

        if json_output:
            typer.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))
            return

        verb = "Would write" if dry_run else "Written"
        console.print(f"[green]{verb}: {len(result.written)} index(es).[/green]")
        if result.unchanged:
            console.print(f"Unchanged: {len(result.unchanged)} index(es).")
        if result.log_appended:
            console.print("Log entry appended.")

    @app.command(name="reindex")
    def reindex(
        target: Path = typer.Argument(Path("."), help="Wiki root directory."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Alias for the ``index`` command."""
        index(target, dry_run, json_output)
