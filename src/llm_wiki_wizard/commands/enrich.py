"""``enrich`` command: auto-draft a needs-review artifact from an ingested source.

Auto-discovered via the commands/ directory scan — no edit to ``cli.py`` or
``commands/__init__.py`` is required.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import typer
from rich.console import Console

console = Console()

# Path to the enrich module inside the vendored tools tree (repo root level).
_REPO_ROOT = Path(__file__).resolve().parents[3]  # src/llm_wiki_wizard/commands/enrich.py → repo root
_ENRICH_PATH = _REPO_ROOT / "tools" / "source-ingest" / "web" / "enrich.py"


def _load_enrich_module():
    spec = importlib.util.spec_from_file_location("_cmd_enrich_web", _ENRICH_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"Cannot load enrich module from {_ENRICH_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def register(app: typer.Typer) -> None:
    @app.command()
    def enrich(
        source_id: str = typer.Argument(..., help="Registry identifier of the already-ingested source."),
        title: str = typer.Option(..., "--title", "-t", help="Human-readable title of the source."),
        url: str = typer.Option(..., "--url", "-u", help="Canonical URL of the source."),
        extract: str = typer.Option("", "--extract", "-e", help="Short text extract for context."),
        artifact_type: str = typer.Option(
            "source-summary",
            "--type",
            help="Artifact type: source-summary or knowledge-note.",
        ),
        output_dir: Path = typer.Option(
            Path("."),
            "--output-dir",
            "-o",
            help="Directory where the draft artifact will be written.",
        ),
    ) -> None:
        """Draft a needs-review artifact from an already-ingested SOURCE_ID."""
        try:
            enrich_mod = _load_enrich_module()
        except ImportError as exc:
            console.print(f"[red]Cannot load enrich module: {exc}[/red]")
            raise typer.Exit(1) from exc

        result = enrich_mod.enrich_source(
            source_id=source_id,
            title=title,
            url=url,
            extract=extract,
            artifact_type=artifact_type,
            output_dir=output_dir,
        )

        if result.skipped:
            console.print(f"[yellow]Enrichment skipped: {result.reason}[/yellow]")
            return

        console.print(f"[green]Draft written: {result.artifact_path}[/green]")
        console.print(f"Status: needs-review  |  source_id: {result.source_id}")
