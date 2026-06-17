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
) -> dict:
    """Build a minimal artifact state dict."""
    fm: dict = {"type": artifact_type, "status": status, "title": title}
    if sources is not None:
        fm["sources"] = sources
    if url:
        fm["url"] = url
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


if __name__ == "__main__":
    unittest.main()
