#!/usr/bin/env python3
"""Canonical frontmatter parser and Markdown tree-walker for the LLM wiki.

This module is the single deep frontmatter-parsing seam that every consumer can
import.  It is intentionally *additive*: today's parsers
(:func:`validate_repo.parse_frontmatter`, ``generate_indexes._parse_frontmatter``,
``interchange.export._parse_frontmatter_raw``, ``interchange.import_._parse_frontmatter``)
continue to work unchanged.  Later slices (#61-#63) migrate those consumers onto
this module; this slice only builds and tests it.

What it parses
--------------
YAML-ish frontmatter delimited by ``---`` fences at the very top of a document:

- **Scalars** with surrounding-quote stripping (``key: "value"`` → ``value``).
- **Block lists** (``key:`` followed by indented ``  - item`` lines).
- **Inline lists** (``key: [a, b, c]``) and the empty list (``key: []``).
- **OKF extension keys** — compound ``namespace:field`` keys such as
  ``llm-wiki:status`` — by partitioning on the *first* ``": "`` (colon-space)
  rather than the first bare ``":"``.  This is what lets
  ``llm-wiki:status: active`` parse to key ``llm-wiki:status`` / value ``active``.
- **Comments** (lines whose first non-space character is ``#``) are ignored.

Why partition on ``": "`` (colon-space)
---------------------------------------
``validate_repo.parse_frontmatter`` splits on the *first* ``":"``, so the line
``llm-wiki:status: active`` would split to key ``llm-wiki`` / value
``status: active`` — wrong for OKF extension keys.  Partitioning on the first
``": "`` instead yields key ``llm-wiki:status`` / value ``active``.  A line with
no ``": "`` but a trailing ``":"`` (e.g. ``tags:``) is still recognised as a
block-list header, and a bare scalar with a final-colon-no-space value is handled
too, so behaviour remains a strict superset of the validator.

Public interface
----------------
- :func:`parse_frontmatter` — parse fence-delimited text into a
  :class:`Frontmatter` (data dict, body string, and optional raw lines).
- :func:`parse_frontmatter_lines` — parse the already-extracted *inner* lines
  (drop-in superset of ``validate_repo.parse_frontmatter``).
- :func:`split_frontmatter` — ``validate_repo``-compatible
  ``(data | None, body_start_index)`` shim.
- :func:`clean_scalar` — strip one layer of matching surrounding quotes.
- :func:`markdown_files` — the one canonical tree-walker honouring
  :data:`SKIP_DIRS`.

Self-contained
--------------
This module imports only :data:`SKIP_DIRS` from ``wiki_spec`` and otherwise has
no dependency on the rest of ``tools/``, so it can be vendored into generated
wikis without pulling in extra modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:  # script invocation: ``tools/`` is on sys.path[0]
    from wiki_spec import SKIP_DIRS
except ImportError:  # imported as ``tools.frontmatter``
    from tools.wiki_spec import SKIP_DIRS


_FENCE = "---"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Frontmatter:
    """Parsed frontmatter for a single document.

    Attributes
    ----------
    data:
        Parsed key→value mapping.  Scalars are ``str``; list-valued fields are
        ``list[str]``.  Empty when the document has no frontmatter fence.
    body:
        The document text *after* the closing fence, with a single trailing
        newline removed by ``splitlines`` semantics (i.e. lines joined by
        ``"\\n"``).  Equals the full text when there is no fence.
    has_frontmatter:
        ``True`` when an opening ``---`` fence was found at line 0.  This
        distinguishes "no fence at all" from "an empty fence" — both yield an
        empty ``data`` dict, but only the latter sets this flag.
    raw_lines:
        The verbatim lines *inside* the fences (between the two ``---``),
        captured only when ``preserve_raw=True`` was passed to
        :func:`parse_frontmatter`.  Enables loss-free round-tripping of
        formatting that the structured ``data`` view normalises away.  Empty
        otherwise.
    body_start:
        0-based line index of the first body line within the original text's
        ``splitlines()``.  ``0`` when there is no fence.
    unterminated:
        ``True`` when an opening ``---`` fence had no matching closing fence.
        In that case the rich ``data`` view still parses the trailing lines
        (additive over the validator), while the validator-compatible
        :func:`split_frontmatter` shim reports an empty dict for parity.
    """

    data: dict[str, object] = field(default_factory=dict)
    body: str = ""
    has_frontmatter: bool = False
    raw_lines: list[str] = field(default_factory=list)
    body_start: int = 0
    unterminated: bool = False


# ---------------------------------------------------------------------------
# Scalar helpers
# ---------------------------------------------------------------------------


def clean_scalar(value: str) -> str:
    """Strip surrounding whitespace and one layer of matching quotes.

    ``'"value"'`` and ``"'value'"`` both return ``value``.  A string whose
    first and last characters are not the *same* quote character is returned
    stripped but otherwise unchanged.  Mirrors ``validate_repo.clean_scalar``.
    """

    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _strip_inline_list(rest: str) -> list[str] | None:
    """Return the items of an inline list ``[a, b]`` or ``None`` if not one.

    ``"[]"`` returns ``[]``; ``"[a, b]"`` returns ``["a", "b"]`` with each item
    quote-stripped.  Anything not wrapped in brackets returns ``None`` so the
    caller can treat it as a scalar.
    """

    stripped = rest.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return None
    inner = stripped[1:-1].strip()
    if not inner:
        return []
    return [clean_scalar(item) for item in inner.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Core line parser
# ---------------------------------------------------------------------------


def parse_frontmatter_lines(lines: list[str]) -> dict[str, object]:
    """Parse the *inner* frontmatter lines (between the fences) into a dict.

    This is a strict superset of ``validate_repo.parse_frontmatter``:

    - Scalars are quote-stripped.
    - ``key:`` with nothing after it, or ``key: []``, yields an empty list.
    - ``key: [a, b]`` yields ``["a", "b"]`` (inline list).
    - Indented ``  - item`` lines append to the most recent block-list key.
    - Compound extension keys (``ns:field``) are preserved by splitting on the
      first ``": "`` (colon-space).  A bare trailing ``":"`` still denotes a
      block-list header.
    - Blank lines and ``#`` comment lines are skipped.

    Unlike the validator, a scalar value that is later followed by ``  - ``
    items is *promoted* to a list (the validator only appended items when the
    key's current value was already a list); this is additive and matches how
    block lists are written in practice (a header line followed by items).
    """

    data: dict[str, object] = {}
    current_key: str | None = None

    for raw_line in lines:
        stripped = raw_line.strip()

        # Skip blanks and comments.
        if not stripped or stripped.startswith("#"):
            continue

        # Block-list item: indented "- value" under the current key.
        if raw_line[:1] in (" ", "\t") and stripped.startswith("- ") and current_key is not None:
            item = clean_scalar(stripped[2:])
            current = data.get(current_key)
            if isinstance(current, list):
                current.append(item)
            else:
                # Promote a (typically empty) scalar header into a list.
                data[current_key] = [item]
            continue

        # Any other indented line is a nested/continuation value we don't model;
        # ignore it but keep the current key context.
        if raw_line[:1] in (" ", "\t"):
            continue

        # Top-level key line.  Partition on the first ": " (colon-space) so that
        # compound extension keys like ``llm-wiki:status`` survive intact.
        if ": " in stripped:
            key, _, value = stripped.partition(": ")
            key = key.strip()
            value = value.strip()
            current_key = key
            inline = _strip_inline_list(value)
            if inline is not None:
                data[key] = inline
            elif value:
                data[key] = clean_scalar(value)
            else:  # ``key: `` with only trailing whitespace after the space
                data[key] = []
            continue

        # Block-list header or empty scalar: ``key:`` (no value, no ": ").
        if stripped.endswith(":"):
            key = stripped[:-1].strip()
            if key:
                current_key = key
                data[key] = []
            continue

        # A line with a colon but no space after it and no trailing colon, e.g.
        # ``key:value`` — split on the first bare ":" for validator parity.
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            current_key = key
            inline = _strip_inline_list(value)
            if inline is not None:
                data[key] = inline
            elif value:
                data[key] = clean_scalar(value)
            else:
                data[key] = []
            continue

        # No colon at all — not a field; ignore (validator parity).

    return data


# ---------------------------------------------------------------------------
# Whole-document parser
# ---------------------------------------------------------------------------


def parse_frontmatter(text: str, *, preserve_raw: bool = False) -> Frontmatter:
    """Parse fence-delimited frontmatter from a whole document.

    Parameters
    ----------
    text:
        Full document text.  Frontmatter, if present, must be a ``---`` fence
        on the very first line and a matching closing ``---`` fence.
    preserve_raw:
        When ``True``, the verbatim lines between the fences are captured in
        :attr:`Frontmatter.raw_lines` for loss-free round-tripping.

    Returns
    -------
    Frontmatter
        With ``has_frontmatter=False`` and the full ``text`` as ``body`` when no
        opening fence is present.  An *unterminated* fence (opening ``---`` with
        no closing fence) parses every remaining line as frontmatter and yields
        an empty body, mirroring ``validate_repo.split_frontmatter``.
    """

    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        return Frontmatter(data={}, body=text, has_frontmatter=False, body_start=0)

    end_index: int | None = None
    for index in range(1, len(lines)):
        if lines[index].strip() == _FENCE:
            end_index = index
            break

    if end_index is None:
        # Unterminated fence: treat the remainder as frontmatter, empty body.
        inner = lines[1:]
        data = parse_frontmatter_lines(inner)
        return Frontmatter(
            data=data,
            body="",
            has_frontmatter=True,
            raw_lines=list(inner) if preserve_raw else [],
            body_start=len(lines),
            unterminated=True,
        )

    inner = lines[1:end_index]
    body_start = end_index + 1
    body = "\n".join(lines[body_start:])
    data = parse_frontmatter_lines(inner)
    return Frontmatter(
        data=data,
        body=body,
        has_frontmatter=True,
        raw_lines=list(inner) if preserve_raw else [],
        body_start=body_start,
    )


def split_frontmatter(
    text: str,
) -> tuple[dict[str, object], int] | tuple[None, int]:
    """``validate_repo``-compatible shim: ``(data | None, body_start_index)``.

    Returns ``(None, 0)`` when there is no opening fence (matching the
    validator's "no frontmatter" sentinel), otherwise the parsed ``data`` dict
    and the 0-based body-start line index.  An unterminated fence returns
    ``({}, len(lines))`` exactly as the validator does — the richer
    :func:`parse_frontmatter` still exposes the parsed trailing lines via its
    :class:`Frontmatter` result, but this shim preserves byte-for-byte
    compatibility with ``validate_repo.split_frontmatter``.
    """

    parsed = parse_frontmatter(text)
    if not parsed.has_frontmatter:
        return None, 0
    if parsed.unterminated:
        return {}, parsed.body_start
    return parsed.data, parsed.body_start


# ---------------------------------------------------------------------------
# Canonical tree-walker
# ---------------------------------------------------------------------------


def markdown_files(root: Path | str) -> list[Path]:
    """Return every governed Markdown file under *root*, sorted.

    A path is governed when **none** of its parts is in :data:`SKIP_DIRS`
    (``.git``, ``.venv``, ``__pycache__``, ``scratch``, ``tmp``, …).  This is
    the one canonical walker; it folds together the duplicated
    ``markdown_files`` / ``_markdown_files`` helpers across the codebase so
    skip-directory policy lives in exactly one place.
    """

    root = Path(root)
    return sorted(
        path
        for path in root.rglob("*.md")
        if not any(part in SKIP_DIRS for part in path.parts)
    )
