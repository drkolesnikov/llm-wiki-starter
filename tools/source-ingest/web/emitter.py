"""Reference-doc emitter for web ingest — catalog item E3 (issue #36).

For a ``"reference"`` :class:`~router.Decision`, this module:

1. Registers the web source via ``registry.register_source(...)`` (#32).
2. Emits a Markdown artifact with ``artifact_type: source-summary`` and
   ``source_tier: reference`` citing the registered source id.

The emitter **refuses** to emit when registration fails and raises
:class:`EmissionError` in that case.

Only the ``"reference"`` outcome is handled here.  ``"enrich"`` and ``"skip"``
decisions must be routed to their respective handlers (outside this module).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Shared source-ingest core (registry wiring).
# ---------------------------------------------------------------------------
# Ensure tools/source-ingest/ is importable regardless of working directory.
_SI_DIR = Path(__file__).resolve().parents[1]
if str(_SI_DIR) not in sys.path:
    sys.path.insert(0, str(_SI_DIR))

from core import wire_registry  # noqa: E402

_register_source = wire_registry()

# Re-export so callers can import from a single place when convenient.
__all__ = ["emit_reference_doc", "EmissionResult", "EmissionError"]


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class EmissionError(Exception):
    """Raised when the emitter cannot proceed (e.g. registration failure)."""


@dataclass
class EmissionResult:
    """Return value of :func:`emit_reference_doc`.

    Attributes
    ----------
    source_id:
        The source id that was registered.
    artifact_path:
        Absolute path to the written Markdown artifact.
    content:
        The Markdown text that was written.
    """

    source_id: str
    artifact_path: Path
    content: str


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, max_len: int = 40) -> str:
    """Return a filesystem-safe slug derived from *text*."""
    slug = _NON_ALNUM.sub("-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "web-source"


def _source_id_from_url(url: str) -> str:
    """Derive a short, stable source id from a URL."""
    # Strip scheme and www prefix.
    bare = re.sub(r"^https?://(www\.)?", "", url)
    return _slugify(bare)


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def emit_reference_doc(
    *,
    decision,  # router.Decision — untyped to avoid a hard import dependency
    registry_path: Path,
    output_dir: Path,
    today: str | None = None,
) -> EmissionResult:
    """Emit a ``source-summary`` / ``reference``-tier Markdown artifact.

    Parameters
    ----------
    decision:
        A :class:`~router.Decision` with ``outcome == "reference"``.  The
        function inspects ``decision.page_title``, ``decision.page_extract``,
        and the originating URL stored on the crawled page.  The URL must be
        passed via ``decision.url`` (set by the caller before invoking this
        function) or inferred from ``page_extract`` — in practice callers
        should set ``decision.url`` explicitly.
    registry_path:
        Absolute path to ``meta/source-registry.md``.
    output_dir:
        Directory where the new Markdown file will be written.  Created if it
        does not exist.
    today:
        ISO-8601 date string for the ``updated`` frontmatter field.  Defaults
        to today's date.

    Returns
    -------
    EmissionResult

    Raises
    ------
    ValueError
        If ``decision.outcome`` is not ``"reference"``.
    EmissionError
        If source registration fails (the file is **not** written).
    """
    if decision.outcome != "reference":
        raise ValueError(
            f"emit_reference_doc requires outcome='reference', got {decision.outcome!r}"
        )

    # Resolve the canonical URL from the decision.
    url: str = getattr(decision, "url", None) or ""
    if not url:
        raise EmissionError("Decision carries no URL — cannot register or emit.")

    title: str = decision.page_title or url
    extract: str = decision.page_extract or ""
    updated: str = today or date.today().isoformat()

    source_id = _source_id_from_url(url)
    slug = _slugify(title)
    filename = f"{slug}.md"

    # --- 1. Register the source first (gate) ---
    result = _register_source(
        source_id=source_id,
        title=title,
        tier="reference",
        derived_path=f"raw/derived/web/{slug}/",
        status="needs-review",
        locator=url,
        format_has_locators=True,
        registry_path=registry_path,
    )

    if not result.ok:
        raise EmissionError(
            f"Source registration failed for {url!r}: missing={result.missing!r}. "
            "Reference doc NOT written."
        )

    # --- 2. Emit the artifact ---
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / filename

    content = _render_reference_doc(
        source_id=source_id,
        title=title,
        url=url,
        extract=extract,
        updated=updated,
    )

    artifact_path.write_text(content, encoding="utf-8")

    return EmissionResult(
        source_id=source_id,
        artifact_path=artifact_path,
        content=content,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_reference_doc(
    *,
    source_id: str,
    title: str,
    url: str,
    extract: str,
    updated: str,
) -> str:
    """Return the Markdown text for a reference source-summary artifact."""
    # Escape pipe characters so they don't break table rows if ever inlined.
    safe_title = title.replace("|", "–")
    safe_extract = extract.replace("|", "–")

    return (
        "---\n"
        "artifact_type: source-summary\n"
        "status: needs-review\n"
        f"source_id: {source_id}\n"
        "source_tier: reference\n"
        f"title: {safe_title!r}\n"
        f"resource: {url}\n"
        f"sources:\n"
        f"  - {source_id}\n"
        f"updated: {updated}\n"
        "---\n"
        "\n"
        f"# {safe_title}\n"
        "\n"
        "## Scope\n"
        "\n"
        f"Source: <{url}>\n"
        "\n"
        f"{safe_extract}\n"
        "\n"
        "## Useful For\n"
        "\n"
        "- Navigation:\n"
        "- Lookup:\n"
        "- Decision support:\n"
        "\n"
        "## Limits\n"
        "\n"
        "- Access limits:\n"
        "- Extraction limits:\n"
        "- Review needed:\n"
        "\n"
        "## Derived Artifacts\n"
        "\n"
        "- Manifest:\n"
        "- Quality report:\n"
        "- Source map:\n"
    )
