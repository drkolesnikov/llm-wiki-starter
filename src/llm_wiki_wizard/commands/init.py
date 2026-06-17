"""``init`` command: initialize a llm-wiki workspace in a target repo."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from ..installer import InstallerError, initialize

console = Console()


def register(app: typer.Typer) -> None:
    @app.command()
    def init(
        target: Path = typer.Argument(Path("."), help="Target repository directory."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing files."),
        yes: bool = typer.Option(False, "--yes", "-y", help="Run without confirmation."),
        json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
    ) -> None:
        """Initialize a llm-wiki workspace in TARGET."""
        if not yes and not dry_run and not json_output:
            typer.confirm(f"Initialize llm-wiki in {target}?", abort=True)
        try:
            result = initialize(target, dry_run=dry_run)
        except InstallerError as exc:
            if json_output:
                typer.echo(json.dumps({"error": str(exc)}, indent=2))
            else:
                console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc

        if json_output:
            typer.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))
            return

        verb = "Would create" if dry_run else "Created"
        console.print(f"[green]{verb} {len(result.created_files)} file(s).[/green]")
        if result.unchanged_files:
            console.print(f"Unchanged: {len(result.unchanged_files)} file(s).")
        if result.conflicts:
            console.print(f"[yellow]Conflicts: {len(result.conflicts)}. See {result.install_report}.[/yellow]")
        console.print(f"Root AGENTS pointer: {result.pointer_action}")
