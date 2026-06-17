"""Tests for tools/preservation.py — pure preservation engine."""
from __future__ import annotations

import unittest

from tools.preservation import evaluate_change, Verdict, Finding


def _state(
    artifact_type: str = "knowledge-note",
    status: str = "active",
    sources: list[str] | None = None,
    body: str = "",
    url: str = "",
    title: str = "test-artifact",
    governance: dict | None = None,
) -> dict:
    """Build a minimal artifact state dict."""
    fm: dict = {"type": artifact_type, "status": status, "title": title}
    if sources is not None:
        fm["sources"] = sources
    if url:
        fm["url"] = url
    if governance is not None:
        fm["governance"] = governance
    return {"frontmatter": fm, "body": body}


# ---------------------------------------------------------------------------
# Helper: assert that a finding with a specific category exists.
# ---------------------------------------------------------------------------

def _has_category(verdict: Verdict, category: str) -> bool:
    return any(f.category == category for f in verdict.findings)


class TestBeforeNone(unittest.TestCase):
    """When before is None (new artifact), never blocked."""

    def test_new_artifact_allowed(self):
        after = _state(status="draft", body="## Claim\nHello\n## Source Support\n")
        verdict = evaluate_change(None, after)
        self.assertFalse(verdict.blocked)
        self.assertEqual(verdict.findings, [])

    def test_new_artifact_with_verified_status_allowed(self):
        after = _state(status="verified")
        verdict = evaluate_change(None, after)
        self.assertFalse(verdict.blocked)

    def test_new_artifact_no_sections_allowed(self):
        after = _state(body="")
        verdict = evaluate_change(None, after)
        self.assertFalse(verdict.blocked)


class TestArtifactDeletion(unittest.TestCase):
    """When after is None (whole-artifact deletion), always blocked."""

    def test_deletion_is_destructive(self):
        before = _state(status="active")
        verdict = evaluate_change(before, None)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "artifact_deletion"))

    def test_deletion_finding_has_artifact_id(self):
        before = _state(title="my-note", status="active")
        verdict = evaluate_change(before, None)
        self.assertEqual(verdict.findings[0].artifact, "my-note")


class TestAdditiveChange(unittest.TestCase):
    """A purely additive after → blocked=False, no findings."""

    def test_additive_body(self):
        before = _state(
            body="## Claim\nOriginal\n## Source Support\nRef\n## Details\nDet\n## Open Questions\nNone\n## Links\nNone",
            sources=["src1"],
            url="https://example.com",
        )
        after = _state(
            body="## Claim\nOriginal\n## Source Support\nRef\n## Details\nDet + more\n## Open Questions\nNone\n## Links\nNone",
            sources=["src1", "src2"],
            url="https://example.com",
        )
        verdict = evaluate_change(before, after)
        self.assertFalse(verdict.blocked)
        self.assertEqual(verdict.findings, [])

    def test_additive_status_upgrade(self):
        before = _state(
            status="draft",
            body="## Claim\nX\n## Source Support\nY\n## Details\nZ\n## Open Questions\nNone\n## Links\nNone",
        )
        after = _state(
            status="active",
            body="## Claim\nX\n## Source Support\nY\n## Details\nZ\n## Open Questions\nNone\n## Links\nNone",
        )
        verdict = evaluate_change(before, after)
        self.assertFalse(verdict.blocked)


class TestDroppedCitation(unittest.TestCase):
    """dropped_citation category."""

    def test_dropped_frontmatter_source(self):
        before = _state(sources=["smith2020", "jones2021"])
        after = _state(sources=["smith2020"])
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "dropped_citation"))
        finding = next(f for f in verdict.findings if f.category == "dropped_citation")
        self.assertIn("jones2021", finding.detail)

    def test_dropped_body_citation(self):
        before = _state(body="See [@smith2020] for details.")
        after = _state(body="See the literature for details.")
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "dropped_citation"))

    def test_citation_retained_not_blocked(self):
        before = _state(sources=["src1"], body="[@src2] is relevant.")
        after = _state(sources=["src1"], body="[@src2] is still relevant.")
        verdict = evaluate_change(before, after)
        self.assertFalse(verdict.blocked)

    def test_multiple_dropped_citations(self):
        before = _state(sources=["a", "b", "c"])
        after = _state(sources=["a"])
        verdict = evaluate_change(before, after)
        categories = [f.category for f in verdict.findings]
        self.assertEqual(categories.count("dropped_citation"), 2)


class TestDeletedRequiredSection(unittest.TestCase):
    """deleted_required_section category."""

    def _knowledge_note_body(self, headings: list[str]) -> str:
        return "\n".join(f"## {h}\ncontent" for h in headings)

    def test_deleted_required_heading(self):
        all_headings = ["Claim", "Source Support", "Details", "Open Questions", "Links"]
        remaining = ["Claim", "Source Support", "Details", "Open Questions"]
        before = _state(artifact_type="knowledge-note",
                        body=self._knowledge_note_body(all_headings))
        after = _state(artifact_type="knowledge-note",
                       body=self._knowledge_note_body(remaining))
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "deleted_required_section"))
        finding = next(f for f in verdict.findings if f.category == "deleted_required_section")
        self.assertIn("Links", finding.detail)

    def test_no_required_sections_for_unknown_type(self):
        before = _state(artifact_type="index", body="## Anything\nContent")
        after = _state(artifact_type="index", body="")
        # index has no required sections, so no finding
        verdict = evaluate_change(before, after)
        self.assertFalse(_has_category(verdict, "deleted_required_section"))

    def test_section_present_not_blocked(self):
        all_headings = ["Claim", "Source Support", "Details", "Open Questions", "Links"]
        before = _state(artifact_type="knowledge-note",
                        body=self._knowledge_note_body(all_headings))
        after = _state(artifact_type="knowledge-note",
                       body=self._knowledge_note_body(all_headings) + "\nExtra content")
        verdict = evaluate_change(before, after)
        self.assertFalse(_has_category(verdict, "deleted_required_section"))

    def test_decision_required_sections(self):
        full = ["Context", "Decision", "Rationale", "Consequences"]
        partial = ["Context", "Decision", "Rationale"]
        before = _state(artifact_type="decision", body=self._knowledge_note_body(full))
        after = _state(artifact_type="decision", body=self._knowledge_note_body(partial))
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "deleted_required_section"))

    def test_section_not_in_before_not_flagged(self):
        # If the section wasn't in before, its absence in after is fine.
        partial = ["Claim", "Source Support", "Details", "Open Questions"]
        before = _state(artifact_type="knowledge-note",
                        body=self._knowledge_note_body(partial))
        after = _state(artifact_type="knowledge-note",
                       body=self._knowledge_note_body(partial))
        verdict = evaluate_change(before, after)
        # No section deletion since nothing was present in before that's gone from after
        self.assertFalse(_has_category(verdict, "deleted_required_section"))


class TestBrokenSourceLink(unittest.TestCase):
    """broken_source_link category."""

    def test_url_removed_from_frontmatter(self):
        before = _state(url="https://example.com/paper.pdf")
        after = _state(url="")
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "broken_source_link"))

    def test_markdown_link_removed(self):
        before = _state(body="See [paper](https://arxiv.org/abs/1234.5678) here.")
        after = _state(body="See the paper here.")
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "broken_source_link"))
        finding = next(f for f in verdict.findings if f.category == "broken_source_link")
        self.assertIn("https://arxiv.org/abs/1234.5678", finding.detail)

    def test_link_retained_not_blocked(self):
        before = _state(url="https://example.com", body="[ref](https://example.com)")
        after = _state(url="https://example.com", body="[ref](https://example.com) updated text")
        verdict = evaluate_change(before, after)
        self.assertFalse(_has_category(verdict, "broken_source_link"))

    def test_adding_link_not_blocked(self):
        before = _state(url="https://example.com")
        after = _state(url="https://example.com", body="[new](https://extra.com)")
        verdict = evaluate_change(before, after)
        self.assertFalse(_has_category(verdict, "broken_source_link"))


class TestVerifiedDowngrade(unittest.TestCase):
    """verified_downgrade category."""

    def test_verified_to_draft(self):
        before = _state(status="verified")
        after = _state(status="draft")
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "verified_downgrade"))

    def test_verified_to_needs_review(self):
        before = _state(status="verified")
        after = _state(status="needs-review")
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "verified_downgrade"))

    def test_verified_to_deprecated(self):
        before = _state(status="verified")
        after = _state(status="deprecated")
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "verified_downgrade"))

    def test_active_to_draft(self):
        before = _state(status="active")
        after = _state(status="draft")
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "verified_downgrade"))

    def test_active_to_verified_upgrade(self):
        before = _state(status="active")
        after = _state(status="verified")
        verdict = evaluate_change(before, after)
        self.assertFalse(_has_category(verdict, "verified_downgrade"))

    def test_draft_to_needs_review_upgrade(self):
        before = _state(status="draft")
        after = _state(status="needs-review")
        verdict = evaluate_change(before, after)
        self.assertFalse(_has_category(verdict, "verified_downgrade"))

    def test_same_status_not_downgrade(self):
        before = _state(status="verified")
        after = _state(status="verified")
        verdict = evaluate_change(before, after)
        self.assertFalse(_has_category(verdict, "verified_downgrade"))

    def test_conflicted_to_draft_not_in_trust_order(self):
        # "conflicted" is not in the trust order, so no downgrade finding
        before = _state(status="conflicted")
        after = _state(status="draft")
        verdict = evaluate_change(before, after)
        self.assertFalse(_has_category(verdict, "verified_downgrade"))

    def test_needs_review_to_active_downgrade(self):
        # needs-review → active is actually an upgrade (active has higher trust)
        before = _state(status="needs-review")
        after = _state(status="active")
        verdict = evaluate_change(before, after)
        self.assertFalse(_has_category(verdict, "verified_downgrade"))

    def test_active_to_needs_review_downgrade(self):
        before = _state(status="active")
        after = _state(status="needs-review")
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "verified_downgrade"))


class TestCombinedFindings(unittest.TestCase):
    """Multiple destructive categories in a single change."""

    def test_multiple_categories(self):
        before = _state(
            artifact_type="knowledge-note",
            status="verified",
            sources=["src1"],
            url="https://example.com",
            body="## Claim\nX\n## Source Support\nY\n## Details\nZ\n## Open Questions\nQ\n## Links\nL",
        )
        after = _state(
            artifact_type="knowledge-note",
            status="draft",
            sources=[],
            url="",
            body="## Claim\nX",  # missing Source Support, Details, etc.
        )
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        categories = {f.category for f in verdict.findings}
        self.assertIn("dropped_citation", categories)
        self.assertIn("deleted_required_section", categories)
        self.assertIn("broken_source_link", categories)
        self.assertIn("verified_downgrade", categories)


class TestPurity(unittest.TestCase):
    """The engine must not import Git or filesystem modules."""

    def test_no_git_import(self):
        import tools.preservation as mod
        import inspect
        src = inspect.getsource(mod)
        self.assertNotIn("import git", src)
        self.assertNotIn("subprocess", src)

    def test_no_filesystem_access(self):
        import tools.preservation as mod
        import inspect
        src = inspect.getsource(mod)
        self.assertNotIn("open(", src)
        self.assertNotIn("Path(", src)


class TestJustificationTrail(unittest.TestCase):
    """F2 — asymmetric friction: justification trail tests.

    Destructive changes are blocked unless the after-state frontmatter carries
    a ``governance.justifications`` entry whose ``covers`` list is a superset
    of every detected destructive category.
    """

    # ------------------------------------------------------------------
    # Helpers to build common before/after pairs
    # ------------------------------------------------------------------

    def _destructive_before(self) -> dict:
        """An artifact with a citation and an active status."""
        return _state(sources=["src1"], status="active", title="note-a")

    def _destructive_after_no_justification(self) -> dict:
        """Drop the citation — destructive, no justification."""
        return _state(sources=[], status="active", title="note-a")

    # ------------------------------------------------------------------
    # 1. Destructive change WITHOUT justification → blocked
    # ------------------------------------------------------------------

    def test_destructive_no_justification_blocked(self):
        """A dropped citation with no justification must be blocked."""
        before = self._destructive_before()
        after = self._destructive_after_no_justification()
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "dropped_citation"))

    def test_destructive_no_governance_block_blocked(self):
        """After-state with no ``governance`` key at all → blocked."""
        before = _state(sources=["src1"], status="verified")
        after = _state(sources=[], status="draft")  # dropped_citation + verified_downgrade
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)

    # ------------------------------------------------------------------
    # 2. Destructive change WITH covering justification → allowed
    # ------------------------------------------------------------------

    def test_destructive_with_covering_justification_allowed(self):
        """A dropped citation with a justification covering dropped_citation → allowed."""
        before = self._destructive_before()
        after = _state(
            sources=[],
            status="active",
            title="note-a",
            governance={
                "justifications": [
                    {
                        "covers": ["dropped_citation"],
                        "reason": "Source retracted; citation removed intentionally.",
                    }
                ]
            },
        )
        verdict = evaluate_change(before, after)
        self.assertFalse(verdict.blocked)
        # Findings are still reported even though not blocked.
        self.assertTrue(_has_category(verdict, "dropped_citation"))

    def test_multi_category_covered_justification_allowed(self):
        """Multiple destructive categories fully covered → allowed."""
        before = _state(sources=["src1"], status="verified", title="note-b")
        after = _state(
            sources=[],
            status="draft",
            title="note-b",
            governance={
                "justifications": [
                    {
                        "covers": ["dropped_citation", "verified_downgrade"],
                        "reason": "Major revision: source removed and status reset.",
                    }
                ]
            },
        )
        verdict = evaluate_change(before, after)
        self.assertFalse(verdict.blocked)

    def test_newest_entry_used_and_covers_all(self):
        """Only the last (newest) justification entry is evaluated."""
        before = _state(sources=["src1"], status="active", title="note-c")
        after = _state(
            sources=[],
            status="active",
            title="note-c",
            governance={
                "justifications": [
                    # First entry does NOT cover
                    {"covers": ["verified_downgrade"], "reason": "Old entry."},
                    # Last (newest) entry DOES cover
                    {"covers": ["dropped_citation"], "reason": "Source retracted."},
                ]
            },
        )
        verdict = evaluate_change(before, after)
        self.assertFalse(verdict.blocked)

    # ------------------------------------------------------------------
    # 3. Justification present but NOT covering the detected change → blocked
    # ------------------------------------------------------------------

    def test_justification_non_covering_blocked(self):
        """A justification that covers a different category does not unblock."""
        before = _state(sources=["src1"], status="active", title="note-d")
        after = _state(
            sources=[],
            status="active",
            title="note-d",
            governance={
                "justifications": [
                    {
                        # covers verified_downgrade, NOT dropped_citation
                        "covers": ["verified_downgrade"],
                        "reason": "Wrong category for this change.",
                    }
                ]
            },
        )
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)
        self.assertTrue(_has_category(verdict, "dropped_citation"))

    def test_justification_partial_coverage_blocked(self):
        """Justification covering only some detected categories → blocked."""
        before = _state(sources=["src1"], status="verified", title="note-e")
        after = _state(
            sources=[],
            status="draft",
            title="note-e",
            governance={
                "justifications": [
                    {
                        # covers dropped_citation but NOT verified_downgrade
                        "covers": ["dropped_citation"],
                        "reason": "Partial justification.",
                    }
                ]
            },
        )
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)

    def test_empty_justifications_list_blocked(self):
        """An empty justifications list does not unblock a destructive change."""
        before = _state(sources=["src1"], status="active", title="note-f")
        after = _state(
            sources=[],
            status="active",
            title="note-f",
            governance={"justifications": []},
        )
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)

    def test_covers_empty_list_in_entry_blocked(self):
        """A justification entry with an empty covers list does not unblock."""
        before = _state(sources=["src1"], status="active", title="note-g")
        after = _state(
            sources=[],
            status="active",
            title="note-g",
            governance={
                "justifications": [{"covers": [], "reason": "Empty covers."}]
            },
        )
        verdict = evaluate_change(before, after)
        self.assertTrue(verdict.blocked)

    def test_covers_superset_still_unblocks(self):
        """Justification covering more than the detected categories still unblocks."""
        before = _state(sources=["src1"], status="active", title="note-h")
        after = _state(
            sources=[],
            status="active",
            title="note-h",
            governance={
                "justifications": [
                    {
                        # covers extra categories beyond what was detected
                        "covers": ["dropped_citation", "verified_downgrade", "artifact_deletion"],
                        "reason": "Broad justification.",
                    }
                ]
            },
        )
        verdict = evaluate_change(before, after)
        self.assertFalse(verdict.blocked)

    # ------------------------------------------------------------------
    # 4. Additive change → no justification required, never blocked
    # ------------------------------------------------------------------

    def test_additive_change_no_justification_needed(self):
        """A purely additive change is never blocked even without a justification."""
        before = _state(
            sources=["src1"],
            status="active",
            body="## Claim\nX\n## Source Support\nY\n## Details\nZ\n## Open Questions\nQ\n## Links\nL",
        )
        after = _state(
            sources=["src1", "src2"],
            status="active",
            body="## Claim\nX\n## Source Support\nY\n## Details\nZ + more\n## Open Questions\nQ\n## Links\nL",
        )
        verdict = evaluate_change(before, after)
        self.assertFalse(verdict.blocked)
        self.assertEqual(verdict.findings, [])

    def test_status_upgrade_no_justification_needed(self):
        """Status upgrade is additive and never requires justification."""
        before = _state(
            status="draft",
            body="## Claim\nX\n## Source Support\nY\n## Details\nZ\n## Open Questions\nQ\n## Links\nL",
        )
        after = _state(
            status="verified",
            body="## Claim\nX\n## Source Support\nY\n## Details\nZ\n## Open Questions\nQ\n## Links\nL",
        )
        verdict = evaluate_change(before, after)
        self.assertFalse(verdict.blocked)
        self.assertEqual(verdict.findings, [])

    def test_new_artifact_never_requires_justification(self):
        """Creating a new artifact (before=None) never requires justification."""
        after = _state(status="active", sources=["src1"])
        verdict = evaluate_change(None, after)
        self.assertFalse(verdict.blocked)


if __name__ == "__main__":
    unittest.main()
