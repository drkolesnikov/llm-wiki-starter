"""Tests for tools/eval/signals/disambiguation.py (issue #44).

Covers:
- Deterministic candidate detection (shared names, co-citation, tag overlap)
  with NO model backend.
- Optional-LLM suggestion path using a stub provider.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from tools.eval import Finding
from tools.eval.signals.disambiguation import SIGNAL, _SIGNAL_ID
from tools.wiki_model import Artifact, RepoModel


ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _artifact(rel_path: str, frontmatter: dict, body: str = "") -> Artifact:
    """Build an Artifact with a real-looking path rooted at ROOT."""
    return Artifact(
        path=ROOT / rel_path,
        frontmatter=frontmatter,
        body=body,
    )


def _model(*artifacts: Artifact) -> RepoModel:
    return RepoModel(root=ROOT, artifacts=list(artifacts), sources={})


# ---------------------------------------------------------------------------
# Deterministic behaviour — no backend required
# ---------------------------------------------------------------------------

class TestSignalMetadata(unittest.TestCase):
    def test_id_and_finding_class(self):
        self.assertEqual("G6-disambiguation", SIGNAL.id)
        self.assertEqual("deterministic", SIGNAL.finding_class)

    def test_run_returns_list(self):
        model = _model()
        result = SIGNAL.run(model)
        self.assertIsInstance(result, list)

    def test_empty_repo_no_findings(self):
        model = _model()
        self.assertEqual([], SIGNAL.run(model))

    def test_single_artifact_no_findings(self):
        model = _model(
            _artifact(
                "knowledge/alpha.md",
                {"artifact_type": "knowledge-note", "title": "Alpha", "tags": ["a", "b"]},
            )
        )
        self.assertEqual([], SIGNAL.run(model))


class TestSharedNameCandidates(unittest.TestCase):
    """Two artifacts with the same title → shared-name candidate finding."""

    def _shared_name_model(self):
        a = _artifact(
            "knowledge/alpha.md",
            {"artifact_type": "knowledge-note", "title": "Transformer"},
        )
        b = _artifact(
            "knowledge/beta.md",
            {"artifact_type": "knowledge-note", "title": "Transformer"},
        )
        return _model(a, b)

    def test_shared_title_produces_candidate(self):
        findings = SIGNAL.run(self._shared_name_model())
        candidate = [f for f in findings if "shared name/alias" in f.explanation]
        self.assertGreater(len(candidate), 0)

    def test_finding_implicates_both_paths(self):
        findings = SIGNAL.run(self._shared_name_model())
        candidate = next(f for f in findings if "shared name/alias" in f.explanation)
        self.assertEqual(2, len(candidate.implicated))

    def test_finding_severity_is_warn(self):
        findings = SIGNAL.run(self._shared_name_model())
        candidate = next(f for f in findings if "shared name/alias" in f.explanation)
        self.assertEqual("warn", candidate.severity)

    def test_shared_alias_also_detected(self):
        a = _artifact(
            "knowledge/alpha.md",
            {"artifact_type": "knowledge-note", "title": "Alpha Concept", "aliases": ["shared-alias"]},
        )
        b = _artifact(
            "knowledge/beta.md",
            {"artifact_type": "knowledge-note", "title": "Beta Concept", "aliases": ["shared-alias"]},
        )
        model = _model(a, b)
        findings = SIGNAL.run(model)
        candidate = [f for f in findings if "shared name/alias" in f.explanation]
        self.assertGreater(len(candidate), 0)

    def test_case_insensitive_name_matching(self):
        a = _artifact(
            "knowledge/alpha.md",
            {"artifact_type": "knowledge-note", "title": "BERT"},
        )
        b = _artifact(
            "knowledge/beta.md",
            {"artifact_type": "knowledge-note", "title": "bert"},
        )
        model = _model(a, b)
        findings = SIGNAL.run(model)
        candidate = [f for f in findings if "shared name/alias" in f.explanation]
        self.assertGreater(len(candidate), 0)

    def test_distinct_names_no_shared_name_candidate(self):
        a = _artifact(
            "knowledge/alpha.md",
            {"artifact_type": "knowledge-note", "title": "Concept Alpha"},
        )
        b = _artifact(
            "knowledge/beta.md",
            {"artifact_type": "knowledge-note", "title": "Concept Beta"},
        )
        model = _model(a, b)
        findings = SIGNAL.run(model)
        candidate = [f for f in findings if "shared name/alias" in f.explanation]
        self.assertEqual([], candidate)


class TestCoCitedCandidates(unittest.TestCase):
    """Two artifacts co-cited together in multiple notes → structural overlap finding."""

    def _co_cited_model(self):
        # Three notes that link both A and B via linked_concepts
        a = _artifact(
            "knowledge/concept-a.md",
            {"artifact_type": "knowledge-note", "title": "Concept A"},
        )
        b = _artifact(
            "knowledge/concept-b.md",
            {"artifact_type": "knowledge-note", "title": "Concept B"},
        )
        # Two notes that co-cite both A and B
        ref1 = _artifact(
            "knowledge/ref1.md",
            {
                "artifact_type": "knowledge-note",
                "title": "Reference 1",
                "linked_concepts": ["Concept A", "Concept B"],
            },
        )
        ref2 = _artifact(
            "knowledge/ref2.md",
            {
                "artifact_type": "knowledge-note",
                "title": "Reference 2",
                "linked_concepts": ["Concept A", "Concept B"],
            },
        )
        return _model(a, b, ref1, ref2)

    def test_co_cited_pair_produces_candidate(self):
        findings = SIGNAL.run(self._co_cited_model())
        co_cited = [f for f in findings if "co-cited" in f.explanation]
        self.assertGreater(len(co_cited), 0)

    def test_co_cited_finding_implicates_both(self):
        findings = SIGNAL.run(self._co_cited_model())
        co_cited = next(f for f in findings if "co-cited" in f.explanation)
        self.assertEqual(2, len(co_cited.implicated))

    def test_single_co_citation_not_flagged(self):
        # Only one referencing note → below _CO_CITE_MIN (2).
        a = _artifact(
            "knowledge/concept-a.md",
            {"artifact_type": "knowledge-note", "title": "Concept A"},
        )
        b = _artifact(
            "knowledge/concept-b.md",
            {"artifact_type": "knowledge-note", "title": "Concept B"},
        )
        ref1 = _artifact(
            "knowledge/ref1.md",
            {
                "artifact_type": "knowledge-note",
                "title": "Reference 1",
                "linked_concepts": ["Concept A", "Concept B"],
            },
        )
        model = _model(a, b, ref1)
        findings = SIGNAL.run(model)
        co_cited = [f for f in findings if "co-cited" in f.explanation]
        self.assertEqual([], co_cited)


class TestTagOverlapCandidates(unittest.TestCase):
    """Two knowledge-notes with high tag Jaccard → tag-overlap candidate finding."""

    def _tag_overlap_model(self, tags_a, tags_b):
        a = _artifact(
            "knowledge/a.md",
            {"artifact_type": "knowledge-note", "title": "Note A", "tags": tags_a},
        )
        b = _artifact(
            "knowledge/b.md",
            {"artifact_type": "knowledge-note", "title": "Note B", "tags": tags_b},
        )
        return _model(a, b)

    def test_identical_tags_flagged(self):
        tags = ["nlp", "transformer", "attention", "bert"]
        model = self._tag_overlap_model(tags, tags)
        findings = SIGNAL.run(model)
        overlap = [f for f in findings if "tag overlap" in f.explanation]
        self.assertGreater(len(overlap), 0)

    def test_high_jaccard_flagged(self):
        # 3 of 4 shared → Jaccard = 3/(3+1+1) = 0.6 → above 0.5
        model = self._tag_overlap_model(
            ["nlp", "transformer", "attention"],
            ["nlp", "transformer", "attention", "bert"],
        )
        findings = SIGNAL.run(model)
        overlap = [f for f in findings if "tag overlap" in f.explanation]
        self.assertGreater(len(overlap), 0)

    def test_low_jaccard_not_flagged(self):
        # 1 of 6 shared → Jaccard ≈ 0.17 → below 0.5
        model = self._tag_overlap_model(
            ["nlp", "transformer", "attention"],
            ["computer-vision", "cnn", "attention"],
        )
        findings = SIGNAL.run(model)
        overlap = [f for f in findings if "tag overlap" in f.explanation]
        self.assertEqual([], overlap)

    def test_non_knowledge_note_excluded(self):
        a = _artifact(
            "knowledge/a.md",
            {"artifact_type": "source-summary", "title": "Source A", "tags": ["nlp", "bert"]},
        )
        b = _artifact(
            "knowledge/b.md",
            {"artifact_type": "source-summary", "title": "Source B", "tags": ["nlp", "bert"]},
        )
        model = _model(a, b)
        findings = SIGNAL.run(model)
        overlap = [f for f in findings if "tag overlap" in f.explanation]
        self.assertEqual([], overlap)

    def test_below_min_tags_excluded(self):
        # Single-tag notes should not be flagged (below _MIN_TAGS = 2).
        model = self._tag_overlap_model(["nlp"], ["nlp"])
        findings = SIGNAL.run(model)
        overlap = [f for f in findings if "tag overlap" in f.explanation]
        self.assertEqual([], overlap)


class TestAllFindingsAreFindings(unittest.TestCase):
    """Every item returned by SIGNAL.run() must be a Finding instance."""

    def test_findings_are_finding_instances(self):
        a = _artifact(
            "knowledge/a.md",
            {
                "artifact_type": "knowledge-note",
                "title": "Duplicate",
                "tags": ["nlp", "bert", "transformer"],
            },
        )
        b = _artifact(
            "knowledge/b.md",
            {
                "artifact_type": "knowledge-note",
                "title": "Duplicate",
                "tags": ["nlp", "bert", "transformer"],
            },
        )
        model = _model(a, b)
        for item in SIGNAL.run(model):
            self.assertIsInstance(item, Finding)
            self.assertEqual(_SIGNAL_ID, item.signal_id)

    def test_signal_id_consistent(self):
        a = _artifact(
            "knowledge/a.md",
            {"artifact_type": "knowledge-note", "title": "Alpha"},
        )
        b = _artifact(
            "knowledge/b.md",
            {"artifact_type": "knowledge-note", "title": "Alpha"},
        )
        model = _model(a, b)
        for finding in SIGNAL.run(model):
            self.assertEqual(_SIGNAL_ID, finding.signal_id)


# ---------------------------------------------------------------------------
# Optional-LLM suggestion path
# ---------------------------------------------------------------------------

class _EnabledStubProvider:
    """Minimal stub that returns a fixed merge suggestion."""

    enabled = True

    def complete(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        return "merge — the two notes cover the same concept"


class TestLLMSuggestionAttaches(unittest.TestCase):
    """With a stub provider, a suggestion finding is attached to each candidate."""

    def _run_with_stub(self, model):
        """Patch get_provider inside the signal module and run."""
        import tools.eval.signals.disambiguation as dis_mod
        original = dis_mod.get_provider
        dis_mod.get_provider = lambda: _EnabledStubProvider()
        try:
            return SIGNAL.run(model)
        finally:
            dis_mod.get_provider = original

    def test_stub_suggestion_attached_to_shared_name(self):
        a = _artifact(
            "knowledge/alpha.md",
            {"artifact_type": "knowledge-note", "title": "Attention"},
        )
        b = _artifact(
            "knowledge/beta.md",
            {"artifact_type": "knowledge-note", "title": "Attention"},
        )
        model = _model(a, b)
        findings = self._run_with_stub(model)

        deterministic = [f for f in findings if f.finding_class == "deterministic"]
        llm = [f for f in findings if f.finding_class == "llm"]
        self.assertGreater(len(deterministic), 0, "expected at least one deterministic finding")
        self.assertGreater(len(llm), 0, "expected at least one LLM suggestion finding")

    def test_suggestion_contains_provider_text(self):
        a = _artifact(
            "knowledge/a.md",
            {"artifact_type": "knowledge-note", "title": "Overlap"},
        )
        b = _artifact(
            "knowledge/b.md",
            {"artifact_type": "knowledge-note", "title": "Overlap"},
        )
        model = _model(a, b)
        findings = self._run_with_stub(model)

        llm_findings = [f for f in findings if f.finding_class == "llm"]
        self.assertTrue(
            any("merge" in f.explanation for f in llm_findings),
            "LLM suggestion text should appear in explanation",
        )

    def test_suggestion_implicates_same_pair(self):
        a = _artifact(
            "knowledge/a.md",
            {"artifact_type": "knowledge-note", "title": "Transformer"},
        )
        b = _artifact(
            "knowledge/b.md",
            {"artifact_type": "knowledge-note", "title": "Transformer"},
        )
        model = _model(a, b)
        findings = self._run_with_stub(model)

        llm_findings = [f for f in findings if f.finding_class == "llm"]
        for lf in llm_findings:
            self.assertEqual(2, len(lf.implicated))


class TestNoBackendDegrades(unittest.TestCase):
    """Without a backend the deterministic candidates still appear; no crash."""

    def test_disabled_provider_no_llm_findings(self):
        # Default get_provider returns DisabledProvider → no LLM findings.
        a = _artifact(
            "knowledge/a.md",
            {"artifact_type": "knowledge-note", "title": "Concept"},
        )
        b = _artifact(
            "knowledge/b.md",
            {"artifact_type": "knowledge-note", "title": "Concept"},
        )
        model = _model(a, b)
        findings = SIGNAL.run(model)
        # Must have at least one candidate finding.
        deterministic = [f for f in findings if f.finding_class == "deterministic"]
        self.assertGreater(len(deterministic), 0)
        # No LLM findings because provider is disabled.
        llm = [f for f in findings if f.finding_class == "llm"]
        self.assertEqual([], llm)

    def test_get_provider_none_degrades_gracefully(self):
        """If get_provider is unavailable entirely, run() still works."""
        import tools.eval.signals.disambiguation as dis_mod
        original = dis_mod.get_provider
        dis_mod.get_provider = None  # type: ignore[assignment]
        try:
            a = _artifact(
                "knowledge/a.md",
                {"artifact_type": "knowledge-note", "title": "Concept"},
            )
            b = _artifact(
                "knowledge/b.md",
                {"artifact_type": "knowledge-note", "title": "Concept"},
            )
            model = _model(a, b)
            findings = SIGNAL.run(model)
            deterministic = [f for f in findings if f.finding_class == "deterministic"]
            self.assertGreater(len(deterministic), 0)
        finally:
            dis_mod.get_provider = original


# ---------------------------------------------------------------------------
# Discovery integration
# ---------------------------------------------------------------------------

class TestAutoDiscovery(unittest.TestCase):
    """The signal is auto-discovered by the eval framework registry."""

    def test_signal_is_discovered(self):
        from tools import eval as eval_pkg
        discovered_ids = [sig.id for _name, sig in eval_pkg.discover_signals()]
        self.assertIn(_SIGNAL_ID, discovered_ids)

    def test_run_suite_includes_disambiguation(self):
        from tools.eval import run_suite
        model = _model()
        # No candidates in an empty model → zero findings, but no crash.
        findings = run_suite(model, selected=[_SIGNAL_ID])
        self.assertIsInstance(findings, list)


if __name__ == "__main__":
    unittest.main()
