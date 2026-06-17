"""``export`` command: render wiki as an OKF v0.1 bundle."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def register(app: typer.Typer) -> None:
    @app.command(name="export")
    def export_cmd(
        target: Path = typer.Argument(Path("."), help="Wiki root directory."),
        out_dir: Path = typer.Option(..., "--out", "-o", help="Destination directory for the OKF bundle."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Export the wiki as an OKF v0.1 bundle into OUT_DIR."""
        if not target.is_dir():
            msg = f"Wiki root does not exist or is not a directory: {target}"
            if json_output:
                typer.echo(json.dumps({"error": msg}, indent=2))
            else:
                console.print(f"[red]{msg}[/red]")
            raise typer.Exit(1)

        meta_dir = target / "meta"
        if not meta_dir.is_dir():
            msg = f"Not a valid wiki root (missing meta/): {target}"
            if json_output:
                typer.echo(json.dumps({"error": msg}, indent=2))
            else:
                console.print(f"[red]{msg}[/red]")
            raise typer.Exit(1)

        try:
            from tools.interchange import export
        except ImportError:
            # Running from within an installed wiki — tools/ is local
            import sys as _sys
            _sys.path.insert(0, str(target / "tools"))
            try:
                from interchange import export  # type: ignore[no-redef]
            except ImportError as exc:
                msg = f"interchange module not available: {exc}"
                if json_output:
                    typer.echo(json.dumps({"error": msg}, indent=2))
                else:
                    console.print(f"[red]{msg}[/red]")
                raise typer.Exit(1) from exc

        result = export(target, out_dir)

        if json_output:
            typer.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))
            return

        console.print(f"[green]Exported {result.artifacts_exported} artifact(s) → {out_dir}[/green]")
        console.print(f"Profile: {result.profile}")
        if result.unresolved_links:
            console.print(f"[yellow]Unresolved links: {len(result.unresolved_links)}[/yellow]")
            for link in result.unresolved_links:
                console.print(f"  • {link}")
        console.print(f"index.md: {'ok' if result.index_written else 'skipped'}")
        console.print(f"log.md:   {'ok' if result.log_written else 'skipped'}")
