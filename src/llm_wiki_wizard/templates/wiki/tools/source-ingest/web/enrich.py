"""Enrichment-agent pattern for web ingest — catalog item E4 (issue #50).

From an already-ingested source this module auto-drafts a ``source-summary``
or ``knowledge-note`` via :func:`tools.llm_provider.get_provider`.

Rules
-----
- Every draft is written with ``status: needs-review``.
- This module NEVER publishes and NEVER advances status on its own.
- When the provider is disabled, the function produces no artifact and
  returns an :class:`EnrichResult` with ``skipped=True`` and
  ``reason="enrichment disabled"``.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# Load llm_provider via explicit path so this works from any working directory.
# ---------------------------------------------------------------------------

_TOOLS_DIR = Path(__file__).resolve().parents[3]  # repo root / tools/..
_PROVIDER_PATH = _TOOLS_DIR / "tools" / "llm_provider.py"


def _load_provider_module():
    spec = importlib.util.spec_from_file_location("_enrich_llm_provider", _PROVIDER_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"Cannot load llm_provider from {_PROVIDER_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_provider_mod = _load_provider_module()
_get_provider = _provider_mod.get_provider


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

__all__ = ["enrich_source", "EnrichResult"]

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, max_len: int = 40) -> str:
    slug = _NON_ALNUM.sub("-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "web-source"


@dataclass
class EnrichResult:
    """Return value of :func:`enrich_source`.

    Attributes
    ----------
    skipped:
        ``True`` when no artifact was written (provider disabled or other
        non-fatal condition).
    reason:
        Human-readable explanation when ``skipped`` is ``True``.
    artifact_path:
        Absolute path to the written Markdown draft, or ``None`` when skipped.
    source_id:
        The source identifier used in the draft, or ``None`` when skipped.
    content:
        The Markdown text that was written, or ``None`` when skipped.
    """

    skipped: bool
    reason: str = ""
    artifact_path: Path | None = None
    source_id: str | None = None
    content: str | None = None


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def enrich_source(
    *,
    source_id: str,
    title: str,
    url: str,
    extract: str = "",
    artifact_type: str = "source-summary",
    output_dir: Path,
    today: str | None = None,
    provider=None,
) -> EnrichResult:
    """Draft a ``source-summary`` or ``knowledge-note`` from an ingested source.

    Parameters
    ----------
    source_id:
        Registry identifier for the already-ingested source.
    title:
        Human-readable title of the source.
    url:
        Canonical URL of the source.
    extract:
        Short text extract from the source for the LLM prompt context.
    artifact_type:
        One of ``"source-summary"`` (default) or ``"knowledge-note"``.
    output_dir:
        Directory where the draft Markdown file will be written.
    today:
        ISO-8601 date string for ``updated`` frontmatter.  Defaults to today.
    provider:
        Optional :class:`~tools.llm_provider.ModelProvider` to inject (for
        testing).  When ``None``, :func:`tools.llm_provider.get_provider` is
        called.

    Returns
    -------
    EnrichResult
        Contains the written artifact path and content, or ``skipped=True``
        with a reason when no artifact is produced.
    """
    if provider is None:
        provider = _get_provider()

    if not provider.enabled:
        return EnrichResult(skipped=True, reason="enrichment disabled")

    updated = today or date.today().isoformat()
    slug = _slugify(title)
    filename = f"{slug}-enrich.md"

    # Build the prompt.
    prompt = (
        f"You are a knowledge-management assistant.\n"
        f"Source: {url}\n"
        f"Title: {title}\n"
        f"Extract: {extract[:400] if extract else '(none)'}\n\n"
        "Draft a concise wiki artifact with the following sections:\n"
        "## Summary\n"
        "## Key Facts\n"
        "## Source Structure\n"
        "## Source References\n"
        "## Related Concepts\n\n"
        "Keep each section brief and factual. Write in a neutral tone."
    )

    body = provider.complete(prompt, system="Be concise and factual.")

    content = _render_draft(
        source_id=source_id,
        title=title,
        url=url,
        artifact_type=artifact_type,
        updated=updated,
        body=body,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / filename
    artifact_path.write_text(content, encoding="utf-8")

    return EnrichResult(
        skipped=False,
        artifact_path=artifact_path,
        source_id=source_id,
        content=content,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_draft(
    *,
    source_id: str,
    title: str,
    url: str,
    artifact_type: str,
    updated: str,
    body: str,
) -> str:
    safe_title = title.replace("|", "–")
    return (
        "---\n"
        f"artifact_type: {artifact_type}\n"
        "status: needs-review\n"
        f"source_id: {source_id}\n"
        f"title: {safe_title!r}\n"
        f"resource: {url}\n"
        f"sources:\n"
        f"  - {source_id}\n"
        f"updated: {updated}\n"
        "---\n"
        "\n"
        f"# {safe_title}\n"
        "\n"
        f"{body.strip()}\n"
    )
