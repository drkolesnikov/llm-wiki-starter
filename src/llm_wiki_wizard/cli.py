"""Command line interface for the LLM Wiki installer."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from .installer import InstallerError, initialize, status as wiki_status


app = typer.Typer(help="Spawn and inspect visible namespaced llm-wiki workspaces.")
console = Console()


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


if __name__ == "__main__":
    app()
