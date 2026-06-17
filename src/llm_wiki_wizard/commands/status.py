"""``status`` command: report llm-wiki installation state for a target repo."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from ..installer import InstallerError, status as wiki_status

console = Console()


def register(app: typer.Typer) -> None:
    @app.command()
    def status(
        target: Path = typer.Argument(Path("."), help="Target repository directory."),
        json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
    ) -> None:
        """Report llm-wiki installation state for TARGET."""
        try:
            result = wiki_status(target)
        except InstallerError as exc:
            if json_output:
                typer.echo(json.dumps({"error": str(exc)}, indent=2))
            else:
                console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc

        if json_output:
            typer.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))
            return

        console.print(f"Wiki exists: {result.wiki_exists}")
        console.print(f"Root AGENTS pointer: {result.root_pointer_exists}")
        console.print(f"Scaffold version: {result.scaffold_version or 'unknown'}")
        console.print(f"Missing managed files: {len(result.missing_managed_files)}")
        console.print(f"Changed managed files: {len(result.changed_managed_files)}")
        console.print(f"Unresolved conflict reports: {len(result.unresolved_conflict_reports)}")
