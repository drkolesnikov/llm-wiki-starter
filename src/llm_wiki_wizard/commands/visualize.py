"""``visualize`` command: render a governance-aware graph viewer for a wiki.

Auto-discovered by the command-loader in ``commands/__init__.py`` — no edits
to ``cli.py`` or ``commands/__init__.py`` are required.

Usage
-----
    llm-wiki visualize [TARGET] [--output OUTPUT] [--json]

Args
----
target
    Path to the wiki root (must contain ``meta/source-registry.md`` or be a
    recognised llm-wiki workspace).  Defaults to the current directory.
--output
    Destination for the output HTML file (or directory when ``--bundle`` is
    used). Defaults to ``<target>/viewer/index.html``.
--json
    Emit machine-readable JSON to stdout instead of the human summary.
    Fields: ``output``, ``data_output``, ``node_count``, ``edge_count``,
    ``status_counts``, ``tier_counts``, ``warnings``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def register(app: typer.Typer) -> None:
    @app.command(name="visualize")
    def visualize(
        target: Path = typer.Argument(
            Path("."),
            help="Wiki root directory.",
        ),
        output: Path = typer.Option(
            None,
            "--output",
            "-o",
            help="Output HTML file path (default: <target>/viewer/index.html).",
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            help="Emit machine-readable JSON report to stdout.",
        ),
    ) -> None:
        """Render a self-contained HTML graph viewer for the wiki at TARGET."""
        target = target.resolve()

        # --- Validate that TARGET looks like an llm-wiki workspace ---
        if not _is_wiki_root(target):
            msg = (
                f"'{target}' does not appear to be an llm-wiki workspace "
                "(expected meta/source-registry.md or llm-wiki/ sub-directory)."
            )
            if json_output:
                typer.echo(json.dumps({"error": msg}, indent=2))
            else:
                console.print(f"[red]Error:[/red] {msg}")
            raise typer.Exit(code=1)

        # --- Determine wiki root (may be <target>/llm-wiki/ if installed) ---
        wiki_root = _resolve_wiki_root(target)

        # --- Import graph extraction & rendering ---
        try:
            from tools.viewer.extract import build_graph
            from tools.viewer.render import render_bundle, _build_graph_data
        except ImportError:
            # Running from inside an installed wiki where tools/ is local.
            sys.path.insert(0, str(wiki_root / "tools"))
            try:
                from viewer.extract import build_graph  # type: ignore[no-redef]
                from viewer.render import render_bundle, _build_graph_data  # type: ignore[no-redef]
            except ImportError as exc:
                msg = f"Cannot import viewer modules: {exc}"
                if json_output:
                    typer.echo(json.dumps({"error": msg}, indent=2))
                else:
                    console.print(f"[red]Error:[/red] {msg}")
                raise typer.Exit(code=1) from exc

        # --- Build graph ---
        graph = build_graph(wiki_root)

        # --- Determine output destination ---
        if output is None:
            out_path = target / "viewer"
        else:
            out_path = output.resolve()
            if out_path.suffix.lower() == ".html":
                # Caller supplied a full file path; use its parent as bundle dir.
                out_path = out_path.parent

        # --- Render ---
        written = render_bundle(graph, out_path)

        # --- Build stats ---
        data = _build_graph_data(graph)

        report = {
            "output":        str(written["html"]),
            "data_output":   str(written["data"]),
            "node_count":    data["node_count"],
            "edge_count":    data["edge_count"],
            "status_counts": data["status_counts"],
            "tier_counts":   data["tier_counts"],
            "warnings":      data["warnings"],
        }

        if json_output:
            typer.echo(json.dumps(report, indent=2, sort_keys=True))
            return

        console.print(f"[green]Viewer written:[/green] {written['html']}")
        console.print(f"  Nodes: {report['node_count']}  |  Edges: {report['edge_count']}")
        if report["warnings"]:
            for w in report["warnings"]:
                console.print(f"  [yellow]⚠[/yellow]  {w}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_wiki_root(path: Path) -> bool:
    """Return True when *path* looks like an llm-wiki workspace.

    Accepted layouts:
    - Direct workspace: ``<path>/meta/source-registry.md`` exists.
    - Installed wiki:   ``<path>/llm-wiki/meta/source-registry.md`` exists.
    - Minimal:          ``<path>/AGENTS.md`` exists (very permissive fallback).
    """
    if not path.is_dir():
        return False
    if (path / "meta" / "source-registry.md").exists():
        return True
    if (path / "llm-wiki" / "meta" / "source-registry.md").exists():
        return True
    # Accept any directory that has an AGENTS.md (common wiki sentinel).
    if (path / "AGENTS.md").exists():
        return True
    return False


def _resolve_wiki_root(path: Path) -> Path:
    """Return the effective wiki root to pass to build_graph().

    If <path>/llm-wiki/meta/source-registry.md exists we drill into the
    sub-directory; otherwise return *path* as-is.
    """
    candidate = path / "llm-wiki"
    if (candidate / "meta" / "source-registry.md").exists():
        return candidate
    return path
