"""
Constraint-bounded web crawler — catalog item E1 (issue #29).

This module ONLY crawls (no router, no emitter).  All network access is
injected via the ``fetch`` callable so the unit tests never touch the network.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlparse


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class CrawlSpec:
    """Parameters that bound the crawl."""

    seed_urls: list[str]
    allowed_hosts: list[str]
    path_prefixes: list[str]
    max_depth: int
    max_pages: int


@dataclass
class Page:
    """A successfully fetched page."""

    url: str
    depth: int
    html: str


@dataclass
class CrawlResult:
    """What the crawl produced."""

    fetched: list[Page] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (url, reason)
    stopped_reason: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_LINK_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


def _canonicalize(url: str) -> str:
    """Return a stable form of *url* suitable for use as a visited-set key."""
    parsed = urlparse(url)
    # Drop the fragment; normalise the path's trailing slash minimally.
    return parsed._replace(fragment="").geturl()


def _extract_links(base_url: str, html: str) -> list[str]:
    """Return absolute URLs found in *html* relative to *base_url*."""
    links: list[str] = []
    for href in _LINK_RE.findall(html):
        href = href.strip()
        if not href or href.startswith("#"):
            continue
        absolute = urljoin(base_url, href)
        # Keep only http/https
        if urlparse(absolute).scheme in ("http", "https"):
            links.append(absolute)
    return links


def _check_constraints(
    url: str, depth: int, spec: CrawlSpec
) -> str | None:
    """Return a skip-reason string if *url* violates any constraint, else None."""
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or "/"

    if host not in spec.allowed_hosts:
        return "host_not_allowed"

    if not any(path.startswith(prefix) for prefix in spec.path_prefixes):
        return "path_not_allowed"

    if depth > spec.max_depth:
        return "depth_exceeded"

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def crawl(spec: CrawlSpec, fetch: Callable[[str], str]) -> CrawlResult:
    """
    Breadth-first crawl bounded by *spec*.

    Parameters
    ----------
    spec:
        Crawl parameters (hosts, path prefixes, depth and page budgets).
    fetch:
        Callable that accepts a URL string and returns the raw HTML string.
        Must raise an exception on failure — this module does not catch fetch
        errors, letting callers decide how to handle them.

    Returns
    -------
    CrawlResult
        Contains every successfully fetched :class:`Page`, every candidate URL
        that was skipped with its reason, and an optional ``stopped_reason``
        (currently only ``"page_budget"``).
    """
    result = CrawlResult()
    visited: set[str] = set()

    # Queue entries: (url, depth)
    queue: deque[tuple[str, int]] = deque()

    for seed in spec.seed_urls:
        canonical = _canonicalize(seed)
        if canonical not in visited:
            queue.append((seed, 0))
            visited.add(canonical)

    while queue:
        # Check page budget BEFORE dequeuing so we can set stopped_reason.
        if len(result.fetched) >= spec.max_pages:
            result.stopped_reason = "page_budget"
            break

        url, depth = queue.popleft()
        canonical = _canonicalize(url)

        # Constraint check BEFORE fetching.
        reason = _check_constraints(url, depth, spec)
        if reason is not None:
            result.skipped.append((url, reason))
            continue

        # Fetch.
        html = fetch(url)
        page = Page(url=url, depth=depth, html=html)
        result.fetched.append(page)

        # Enqueue discovered links (constraint-checked lazily at pop time).
        if depth < spec.max_depth:
            for link in _extract_links(url, html):
                link_canonical = _canonicalize(link)
                if link_canonical not in visited:
                    visited.add(link_canonical)
                    queue.append((link, depth + 1))

    return result
