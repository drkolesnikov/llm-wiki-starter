"""Preservation engine: pure, diff-aware destructive-change detector.

`evaluate_change(before, after)` compares two artifact states and returns a
Verdict indicating whether the transition is destructive.  The engine is PURE —
it reads only the states passed in and performs no Git or filesystem access.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from tools.wiki_spec import REQUIRED_SECTIONS

# ---------------------------------------------------------------------------
# Trust order for verified-downgrade detection (higher index = higher trust).
# ---------------------------------------------------------------------------
_TRUST_ORDER: list[str] = ["draft", "needs-review", "active", "verified"]

# A status is considered "trusted" if it appears in the trust order.
# Moving from a higher-trust status to a lower-trust one (or to "deprecated"
# from "verified") is a verified downgrade.


@dataclass
class Finding:
    """A single destructive-change finding."""

    category: str  # dropped_citation | deleted_required_section | broken_source_link | verified_downgrade | artifact_deletion
    artifact: str  # identifier / path of the affected artifact
    detail: str    # human-readable description


@dataclass
class Verdict:
    """Result returned by evaluate_change."""

    blocked: bool
    findings: list[Finding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_citations(frontmatter: dict[str, Any], body: str) -> set[str]:
    """Return the set of all source ids cited in this artifact state.

    Sources can appear in:
    - frontmatter key ``sources`` (list of source ids)
    - inline body citations like ``[@source-id]`` or ``[source-id]``
    """
    ids: set[str] = set()

    # Frontmatter sources list
    sources = frontmatter.get("sources", [])
    if isinstance(sources, list):
        for s in sources:
            if s:
                ids.add(str(s).strip())

    # Body citations: [@id] or bare [id] patterns that look like source refs.
    # We match [@word...] and [word...] where the content is slug-like.
    for match in re.finditer(r"\[@?([\w][\w\-/:.]*)\]", body):
        ids.add(match.group(1).strip())

    return ids


def _extract_source_links(frontmatter: dict[str, Any], body: str) -> set[str]:
    """Return all registered-source references (url / id strings) in this state.

    A registered-source reference is any URL or source id that appears in:
    - frontmatter ``url`` / ``doi`` / ``arxiv`` fields
    - Markdown link targets in the body: ``[text](url)``
    """
    refs: set[str] = set()

    for key in ("url", "doi", "arxiv", "link"):
        val = frontmatter.get(key)
        if val and isinstance(val, str):
            refs.add(val.strip())

    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", body):
        href = match.group(1).strip()
        if href:
            refs.add(href)

    return refs


def _section_headings(body: str) -> set[str]:
    """Return the set of top-level ## heading titles found in *body*."""
    headings: set[str] = set()
    for line in body.splitlines():
        m = re.match(r"^##\s+(.+)$", line.strip())
        if m:
            headings.add(m.group(1).strip())
    return headings


def _trust_index(status: str) -> int:
    """Return the trust index for a status, or -1 if not in the trust order."""
    try:
        return _TRUST_ORDER.index(status)
    except ValueError:
        return -1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_change(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> Verdict:
    """Evaluate a state transition from *before* to *after*.

    Parameters
    ----------
    before:
        The previous artifact state, or ``None`` when a new artifact is being
        created.  Each state is a dict with keys ``frontmatter`` (dict) and
        ``body`` (str).
    after:
        The new artifact state, or ``None`` when the artifact is being deleted.

    Returns
    -------
    Verdict
        ``blocked=True`` if any destructive finding was detected.
    """
    findings: list[Finding] = []

    # ------------------------------------------------------------------
    # Whole-artifact deletion: after is None
    # ------------------------------------------------------------------
    if after is None:
        artifact_id = _artifact_id(before)
        findings.append(Finding(
            category="artifact_deletion",
            artifact=artifact_id,
            detail="Artifact deleted entirely.",
        ))
        return Verdict(blocked=True, findings=findings)

    # ------------------------------------------------------------------
    # New artifact (before is None): never emit destructive findings.
    # Structural-only rules could be checked here in future slices.
    # ------------------------------------------------------------------
    if before is None:
        return Verdict(blocked=False, findings=[])

    # ------------------------------------------------------------------
    # Diff: compare before → after
    # ------------------------------------------------------------------
    before_fm: dict[str, Any] = before.get("frontmatter", {})
    before_body: str = before.get("body", "")
    after_fm: dict[str, Any] = after.get("frontmatter", {})
    after_body: str = after.get("body", "")

    artifact_id = _artifact_id(before)

    # 1. dropped_citation ------------------------------------------------
    before_citations = _extract_citations(before_fm, before_body)
    after_citations = _extract_citations(after_fm, after_body)
    for dropped in sorted(before_citations - after_citations):
        findings.append(Finding(
            category="dropped_citation",
            artifact=artifact_id,
            detail=f"Citation '{dropped}' present in before but absent in after.",
        ))

    # 2. deleted_required_section ----------------------------------------
    artifact_type: str = str(before_fm.get("type", "")).strip()
    required: list[str] = REQUIRED_SECTIONS.get(artifact_type, [])
    before_headings = _section_headings(before_body)
    after_headings = _section_headings(after_body)
    for heading in required:
        if heading in before_headings and heading not in after_headings:
            findings.append(Finding(
                category="deleted_required_section",
                artifact=artifact_id,
                detail=f"Required section '## {heading}' (type '{artifact_type}') deleted.",
            ))

    # 3. broken_source_link ----------------------------------------------
    before_links = _extract_source_links(before_fm, before_body)
    after_links = _extract_source_links(after_fm, after_body)
    for broken in sorted(before_links - after_links):
        findings.append(Finding(
            category="broken_source_link",
            artifact=artifact_id,
            detail=f"Source link '{broken}' resolved in before but is absent in after.",
        ))

    # 4. verified_downgrade ----------------------------------------------
    before_status = str(before_fm.get("status", "")).strip()
    after_status = str(after_fm.get("status", "")).strip()
    _check_verified_downgrade(before_status, after_status, artifact_id, findings)

    blocked = bool(findings)
    return Verdict(blocked=blocked, findings=findings)


def _artifact_id(state: dict[str, Any] | None) -> str:
    """Return a human-readable identifier for the artifact."""
    if state is None:
        return "<unknown>"
    fm = state.get("frontmatter", {})
    for key in ("id", "title", "path"):
        val = fm.get(key)
        if val:
            return str(val)
    return state.get("path", "<unknown>")


def _check_verified_downgrade(
    before_status: str,
    after_status: str,
    artifact_id: str,
    findings: list[Finding],
) -> None:
    """Append a finding if the status transition is a verified downgrade."""
    if before_status == after_status:
        return
    if not before_status or not after_status:
        return

    before_idx = _trust_index(before_status)
    after_idx = _trust_index(after_status)

    # verified → deprecated is a downgrade even though deprecated is not in the
    # trust order (after_idx == -1).
    if before_status == "verified" and after_status == "deprecated":
        findings.append(Finding(
            category="verified_downgrade",
            artifact=artifact_id,
            detail=(
                f"Status downgraded from '{before_status}' to '{after_status}' "
                f"(verified → deprecated)."
            ),
        ))
        return

    # Both must be in the trust order for a numerical comparison.
    if before_idx == -1 or after_idx == -1:
        return

    if after_idx < before_idx:
        findings.append(Finding(
            category="verified_downgrade",
            artifact=artifact_id,
            detail=(
                f"Status downgraded from '{before_status}' to '{after_status}'."
            ),
        ))
