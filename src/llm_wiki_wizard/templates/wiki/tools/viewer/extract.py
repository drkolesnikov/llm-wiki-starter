#!/usr/bin/env python3
"""Governance-aware graph extraction for the LLM wiki viewer.

``build_graph(root) -> GraphModel`` walks the repository under *root*, parses
every Markdown artifact, and produces a :class:`GraphModel` whose nodes carry
governance metadata (status, source_tier, sources, description, …) and whose
edges represent directed links extracted from both standard Markdown links and
``[[wikilink]]``/``linked_concepts`` frontmatter lists.

Extraction only — no rendering, no CLI (those are #51).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Try both invocation contexts (script vs. package import).
# ---------------------------------------------------------------------------
try:
    from wiki_spec import ALLOWED_STATUSES, ALLOWED_SOURCE_TIERS
except ImportError:
    from tools.wiki_spec import ALLOWED_STATUSES, ALLOWED_SOURCE_TIERS

try:
    from frontmatter import markdown_files as _canonical_markdown_files
    from validate_repo import registered_sources, split_frontmatter, source_values
except ImportError:
    from tools.frontmatter import markdown_files as _canonical_markdown_files
    from tools.validate_repo import registered_sources, split_frontmatter, source_values


# ---------------------------------------------------------------------------
# Constants & compiled patterns
# ---------------------------------------------------------------------------

# Marker placed on edges whose target did not resolve to a known node.
UNRESOLVED_MARKER: str = "unresolved"

# Marker used when a status / tier value falls outside the closed vocabulary.
UNKNOWN_VALUE: str = "unknown"

# Zero-source flag value.
ZERO_SOURCE_FLAG: str = "zero-source"

_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)#?]+?)(?:[#?][^)]*)?\)")
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]")
_CODE_SPAN_RE = re.compile(r"`+[^`]+`+")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

LinkKind = Literal["markdown", "wikilink"]


@dataclass
class NodeModel:
    """A single artifact node in the graph."""

    #: Stable identifier derived from the artifact path relative to the repo root.
    node_id: str

    #: Raw filesystem path (absolute).
    path: Path

    #: ``artifact_type`` frontmatter value, or ``None`` if absent.
    artifact_type: str | None

    #: ``title`` frontmatter value, or the file stem when absent.
    title: str

    #: Status from the closed ALLOWED_STATUSES vocabulary, or ``"unknown"``.
    status: str

    #: Tags list (may be empty).
    tags: list[str]

    #: Optional one-sentence description.
    description: str | None

    #: Resolved source IDs from ``sources`` frontmatter.
    sources: list[str]

    #: ``source_count`` as declared in frontmatter, or len(sources) when absent.
    source_count: int

    #: Highest-priority tier found among cited sources in the registry,
    #: or ``"unknown"`` when no sources are registered, or ``ZERO_SOURCE_FLAG``
    #: when this is a knowledge-note with zero sources.
    source_tier: str

    #: Artifact body text (everything after the frontmatter fence).
    body: str

    #: Outgoing edges (populated after all nodes are built).
    edges: list[EdgeModel] = field(default_factory=list)

    #: Incoming backlink edges (populated after all edges are built).
    backlinks: list[EdgeModel] = field(default_factory=list)


@dataclass
class EdgeModel:
    """A directed link between two artifact nodes."""

    #: node_id of the source artifact.
    source_id: str

    #: node_id of the target artifact, or ``UNRESOLVED_MARKER`` when unknown.
    target_id: str

    #: Raw link text as it appeared in the document (href or wikilink label).
    raw_target: str

    #: Whether the edge was extracted from a Markdown link or a wikilink.
    kind: LinkKind

    #: True when target_id maps to a known node in the graph.
    resolved: bool


@dataclass
class GraphModel:
    """Complete governance-aware graph of the wiki repository."""

    root: Path
    nodes: dict[str, NodeModel] = field(default_factory=dict)

    def node_by_id(self, node_id: str) -> NodeModel | None:
        return self.nodes.get(node_id)


# ---------------------------------------------------------------------------
# Tier resolution helpers
# ---------------------------------------------------------------------------

# Priority order: lower index = higher priority.
_TIER_PRIORITY: list[str] = ["primary", "secondary", "reference", "background", "restricted"]


def _resolve_tier(sources: list[str], registry: dict[str, dict[str, str]], artifact_type: str | None) -> str:
    """Return the effective source_tier for a node.

    - If artifact_type == "knowledge-note" and sources is empty: ZERO_SOURCE_FLAG.
    - If no cited source appears in the registry: "unknown".
    - Otherwise: the highest-priority tier among cited registered sources.
    """
    if not sources:
        if artifact_type == "knowledge-note":
            return ZERO_SOURCE_FLAG
        return UNKNOWN_VALUE

    tiers_found: list[str] = []
    for src_id in sources:
        entry = registry.get(src_id)
        if entry is None:
            continue
        tier = entry.get("tier", "").strip()
        if tier in ALLOWED_SOURCE_TIERS:
            tiers_found.append(tier)
        else:
            tiers_found.append(UNKNOWN_VALUE)

    if not tiers_found:
        return UNKNOWN_VALUE

    # Pick the highest-priority known tier; if all unknown, return "unknown".
    for priority_tier in _TIER_PRIORITY:
        if priority_tier in tiers_found:
            return priority_tier
    return UNKNOWN_VALUE


# ---------------------------------------------------------------------------
# Link extraction helpers
# ---------------------------------------------------------------------------

def _strip_code_spans(text: str) -> str:
    """Remove inline code spans so link patterns inside them are ignored."""
    return _CODE_SPAN_RE.sub("", text)


def _extract_markdown_links(body: str) -> list[str]:
    """Return href targets from standard Markdown links in *body*."""
    clean = _strip_code_spans(body)
    return [m.group(2).strip() for m in _LINK_RE.finditer(clean)]


def _extract_wikilinks(body: str, frontmatter: dict) -> list[str]:
    """Return wikilink targets from ``[[...]]`` in *body* and ``linked_concepts``."""
    clean = _strip_code_spans(body)
    results: list[str] = [m.group(1).strip() for m in _WIKILINK_RE.finditer(clean)]

    # Also harvest from frontmatter linked_concepts / linked_reviews lists.
    for key in ("linked_concepts", "linked_reviews"):
        raw = frontmatter.get(key)
        if not raw:
            continue
        items: list[str] = raw if isinstance(raw, list) else [str(raw)]
        for item in items:
            # items may themselves be "[[...]]" strings.
            for m in _WIKILINK_RE.finditer(str(item)):
                results.append(m.group(1).strip())
            # If no wikilink syntax found but the item is a plain string, use as-is.
            if not _WIKILINK_RE.search(str(item)):
                plain = str(item).strip()
                if plain:
                    results.append(plain)

    return results


# ---------------------------------------------------------------------------
# Node-ID / path resolution helpers
# ---------------------------------------------------------------------------

def _node_id(path: Path, root: Path) -> str:
    """Derive a stable node ID from the relative POSIX path.

    Both *path* and *root* are resolved before computing the relative path so
    that symlinks (e.g. macOS ``/var`` → ``/private/var``) don't cause mismatches.
    """
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        # Fallback: try without resolving (works when both are already canonical).
        return path.relative_to(root).as_posix()


def _resolve_href(href: str, source_path: Path, root: Path, node_ids: set[str]) -> str | None:
    """Resolve a Markdown href relative to *source_path* into a node_id.

    Returns the node_id string if it maps to a known node, else None.
    Skips absolute URLs and anchors.
    """
    if href.startswith(("http://", "https://", "mailto:", "#", "/")):
        return None
    try:
        resolved = (source_path.parent / href).resolve()
        # Resolve root too so macOS /var -> /private/var symlinks don't mismatch.
        resolved_root = root.resolve()
        candidate = resolved.relative_to(resolved_root).as_posix()
        if candidate in node_ids:
            return candidate
    except (ValueError, OSError):
        pass
    return None


def _resolve_wikilink(label: str, node_ids: set[str]) -> str | None:
    """Resolve a wikilink label to a node_id by matching file stems case-insensitively."""
    # Normalise: lowercase, replace spaces with hyphens.
    normalised = label.lower().replace(" ", "-")
    for nid in node_ids:
        stem = Path(nid).stem.lower()
        if stem == normalised:
            return nid
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_graph(root: str | Path) -> GraphModel:
    """Parse all Markdown artifacts under *root* into a :class:`GraphModel`.

    Steps:
    1. Parse frontmatter + body for every artifact.
    2. Build NodeModel for each (governance fields, tier resolution).
    3. Extract directed edges from Markdown links and wikilinks.
    4. Invert edges to populate backlinks.

    Never raises on missing fields, unresolved links, or unknown enum values.
    """
    root = Path(root)
    registry: dict[str, dict[str, str]] = registered_sources(root)
    graph = GraphModel(root=root)

    # --- Pass 1: build nodes ---
    paths = _canonical_markdown_files(root)
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        frontmatter_raw, body_start = split_frontmatter(text)
        fm: dict = frontmatter_raw if isinstance(frontmatter_raw, dict) else {}
        body_lines = text.splitlines()[body_start:]
        body = "\n".join(body_lines)

        # Core fields — tolerant of missing values.
        nid = _node_id(path, root)
        artifact_type = fm.get("artifact_type") or None
        if isinstance(artifact_type, str):
            artifact_type = artifact_type.strip() or None

        raw_title = fm.get("title") or path.stem
        title = str(raw_title).strip() or path.stem

        raw_status = fm.get("status", "")
        status_str = str(raw_status).strip() if raw_status else ""
        status = status_str if status_str in ALLOWED_STATUSES else UNKNOWN_VALUE if status_str else UNKNOWN_VALUE

        tags_raw = fm.get("tags", [])
        tags: list[str] = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else (
            [str(tags_raw).strip()] if tags_raw else []
        )

        description_raw = fm.get("description")
        description: str | None = str(description_raw).strip() if description_raw else None

        sources: list[str] = source_values(fm)
        declared_count = fm.get("source_count")
        try:
            source_count = int(declared_count) if declared_count is not None else len(sources)
        except (ValueError, TypeError):
            source_count = len(sources)

        source_tier = _resolve_tier(sources, registry, artifact_type)

        graph.nodes[nid] = NodeModel(
            node_id=nid,
            path=path,
            artifact_type=artifact_type,
            title=title,
            status=status,
            tags=tags,
            description=description,
            sources=sources,
            source_count=source_count,
            source_tier=source_tier,
            body=body,
        )

    node_ids: set[str] = set(graph.nodes.keys())

    # --- Pass 2: extract edges ---
    all_edges: list[EdgeModel] = []
    for nid, node in graph.nodes.items():
        path = node.path
        fm_for_links: dict = {}
        try:
            text = path.read_text(encoding="utf-8")
            fm_raw, body_start = split_frontmatter(text)
            fm_for_links = fm_raw if isinstance(fm_raw, dict) else {}
        except OSError:
            pass

        # Markdown links from body.
        for href in _extract_markdown_links(node.body):
            target_id = _resolve_href(href, path, root, node_ids)
            if target_id is None:
                # Skip external URLs; flag internal unresolved paths.
                if href.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                resolved_flag = False
                effective_target = UNRESOLVED_MARKER
            else:
                resolved_flag = True
                effective_target = target_id

            edge = EdgeModel(
                source_id=nid,
                target_id=effective_target,
                raw_target=href,
                kind="markdown",
                resolved=resolved_flag,
            )
            node.edges.append(edge)
            all_edges.append(edge)

        # Wikilinks from body + frontmatter lists.
        for label in _extract_wikilinks(node.body, fm_for_links):
            target_id = _resolve_wikilink(label, node_ids)
            if target_id is None:
                resolved_flag = False
                effective_target = UNRESOLVED_MARKER
            else:
                resolved_flag = True
                effective_target = target_id

            edge = EdgeModel(
                source_id=nid,
                target_id=effective_target,
                raw_target=label,
                kind="wikilink",
                resolved=resolved_flag,
            )
            node.edges.append(edge)
            all_edges.append(edge)

    # --- Pass 3: invert edges into backlinks ---
    for edge in all_edges:
        if edge.resolved and edge.target_id in graph.nodes:
            graph.nodes[edge.target_id].backlinks.append(edge)

    return graph
