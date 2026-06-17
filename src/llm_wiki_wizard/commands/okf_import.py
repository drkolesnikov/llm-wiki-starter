"""``import`` command: quarantine an OKF bundle into the staging area."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def register(app: typer.Typer) -> None:
    @app.command(name="import")
    def import_cmd(
        bundle: Path = typer.Argument(..., help="Path to the OKF bundle directory to import."),
        staging: Path = typer.Option(..., "--staging", "-s", help="Staging area (quarantine) directory."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Import an OKF bundle into STAGING as quarantined artifacts (status: needs-review)."""
        if not bundle.exists() or not bundle.is_dir():
            msg = f"Bundle path does not exist or is not a directory: {bundle}"
            if json_output:
                typer.echo(json.dumps({"error": msg}, indent=2))
            else:
                console.print(f"[red]{msg}[/red]")
            raise typer.Exit(1)

        try:
            from tools.interchange import import_bundle
        except ImportError:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
            try:
                from interchange import import_bundle  # type: ignore[no-redef]
            except ImportError as exc:
                msg = f"interchange module not available: {exc}"
                if json_output:
                    typer.echo(json.dumps({"error": msg}, indent=2))
                else:
                    console.print(f"[red]{msg}[/red]")
                raise typer.Exit(1) from exc

        result = import_bundle(bundle, staging)

        if json_output:
            typer.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))
            return

        console.print(
            f"[green]Staged {result.artifacts_staged} artifact(s) → {staging}[/green]"
        )
        if result.skipped:
            console.print(f"[yellow]Skipped: {result.skipped}[/yellow]")
        if result.notes:
            console.print(f"[yellow]Notes ({len(result.notes)}):[/yellow]")
            for note in result.notes:
                console.print(f"  • {note}")
