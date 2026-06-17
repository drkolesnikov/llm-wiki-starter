"""Per-page routing for web ingest — catalog item E2 (issue #36).

``route_page`` inspects a crawled :class:`~crawler.Page` and returns a
:class:`Decision` indicating one of three outcomes:

``enrich``
    The page should enrich an existing wiki artifact identified by
    ``target_artifact_id``.

``reference``
    The page has enough standalone value to become a new ``source-summary``
    reference document (catalog item E3 handled by ``emitter.py``).

``skip``
    The page is not worth processing.  No artifact is emitted; the URL is
    recorded as visited.

All three outcomes carry a ``rationale`` string for audit purposes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

# Outcome literals
Outcome = Literal["enrich", "reference", "skip"]

# HTML tag-stripping pattern (good enough for signal extraction; not a parser).
_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)

# Heuristic: pages this short are probably error / redirect stubs.
_MIN_TEXT_CHARS = 80

# Heuristic: "thin" pages that aren't worth a reference doc of their own.
_REFERENCE_MIN_CHARS = 400


def _text_content(html: str) -> str:
    """Return approximate visible text by stripping HTML tags."""
    text = _TAG_RE.sub(" ", html)
    # Collapse whitespace.
    return " ".join(text.split())


def _extract_title(html: str) -> str:
    """Extract the page title from the <title> tag or first <h1>."""
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.IGNORECASE)
    if m:
        return _TAG_RE.sub("", m.group(1)).strip()
    return ""


@dataclass
class Decision:
    """Routing decision for a single crawled page.

    Attributes
    ----------
    outcome:
        One of ``"enrich"``, ``"reference"``, or ``"skip"``.
    rationale:
        Human-readable explanation of why this outcome was chosen.
    target_artifact_id:
        For ``"enrich"`` decisions: the identifier of the existing artifact the
        page's content should be merged into.  ``None`` for other outcomes.
    page_title:
        Best-effort title extracted from the page HTML.  Populated for
        ``"reference"`` decisions; ``None`` otherwise.
    page_extract:
        Short text extract (first ~300 chars of visible text) for
        ``"reference"`` decisions.  ``None`` otherwise.
    """

    outcome: Outcome
    rationale: str
    target_artifact_id: str | None = field(default=None)
    page_title: str | None = field(default=None)
    page_extract: str | None = field(default=None)


def route_page(
    page,  # crawler.Page — kept untyped to avoid a hard import dependency
    model: dict | None = None,
) -> Decision:
    """Route a crawled *page* to an ingest outcome.

    Parameters
    ----------
    page:
        A :class:`crawler.Page` instance (``url``, ``depth``, ``html``).
    model:
        Optional mapping of ``{artifact_id: [keyword, ...]}`` that the router
        uses to attempt ``enrich`` matching.  When *model* is ``None`` or no
        match is found, the router falls back to ``"reference"`` or ``"skip"``.

    Returns
    -------
    Decision
        Exactly one of ``enrich | reference | skip``, with a non-empty
        ``rationale``.
    """
    html = page.html
    url = page.url
    text = _text_content(html)

    # --- guard: stub / empty page → skip ---
    if len(text) < _MIN_TEXT_CHARS:
        return Decision(
            outcome="skip",
            rationale=f"Visible text too short ({len(text)} chars < {_MIN_TEXT_CHARS}); likely stub or redirect.",
        )

    # --- attempt enrich matching via provided model ---
    if model:
        url_lower = url.lower()
        text_lower = text.lower()
        for artifact_id, keywords in model.items():
            if not keywords:
                continue
            matched = [kw for kw in keywords if kw.lower() in url_lower or kw.lower() in text_lower]
            if len(matched) >= max(1, len(keywords) // 2):
                return Decision(
                    outcome="enrich",
                    rationale=(
                        f"Page matches artifact {artifact_id!r} "
                        f"on keyword(s): {matched!r}."
                    ),
                    target_artifact_id=artifact_id,
                )

    # --- fallback: reference or skip based on content volume ---
    if len(text) < _REFERENCE_MIN_CHARS:
        return Decision(
            outcome="skip",
            rationale=(
                f"Visible text ({len(text)} chars) below reference threshold "
                f"({_REFERENCE_MIN_CHARS} chars) and no enrich match found."
            ),
        )

    title = _extract_title(html)
    extract = text[:300].strip()

    return Decision(
        outcome="reference",
        rationale=(
            f"Sufficient standalone content ({len(text)} chars); "
            "no enrich match — emitting reference doc."
        ),
        page_title=title or None,
        page_extract=extract or None,
    )
