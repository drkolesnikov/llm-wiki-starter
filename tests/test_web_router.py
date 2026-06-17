"""Tests for tools/source-ingest/web/router.py — issue #36."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTER_PATH = ROOT / "tools" / "source-ingest" / "web" / "router.py"


def _load_router():
    spec = importlib.util.spec_from_file_location("web_router", ROUTER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


router_mod = _load_router()
route_page = router_mod.route_page
Decision = router_mod.Decision


# ---------------------------------------------------------------------------
# Minimal stub for crawler.Page (avoids importing the crawler).
# ---------------------------------------------------------------------------

def _make_page(url: str, html: str, depth: int = 0):
    page = types.SimpleNamespace()
    page.url = url
    page.html = html
    page.depth = depth
    return page


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_STUB_HTML = "<html><body><p>Hi</p></body></html>"  # < MIN_TEXT_CHARS

_SHORT_HTML = (
    "<html><body><p>"
    + "x" * 100
    + "</p></body></html>"
)  # >= MIN_TEXT_CHARS but < REFERENCE_MIN_CHARS

_RICH_HTML = (
    "<html><head><title>Deep Learning Basics</title></head><body>"
    "<h1>Deep Learning Basics</h1>"
    "<p>" + "Deep learning is a subset of machine learning. " * 20 + "</p>"
    "</body></html>"
)

_ENRICH_HTML = (
    "<html><body>"
    "<p>transformer attention mechanism self-attention " * 15 + "</p>"
    "</body></html>"
)


# ---------------------------------------------------------------------------
# Tests: Decision shape
# ---------------------------------------------------------------------------


class TestDecisionShape(unittest.TestCase):
    """Every outcome must carry a non-empty rationale."""

    def _assert_valid_decision(self, decision):
        self.assertIn(decision.outcome, {"enrich", "reference", "skip"})
        self.assertIsInstance(decision.rationale, str)
        self.assertGreater(len(decision.rationale), 0, "rationale must be non-empty")

    def test_skip_has_rationale(self):
        d = route_page(_make_page("https://example.com/", _STUB_HTML))
        self._assert_valid_decision(d)

    def test_reference_has_rationale(self):
        d = route_page(_make_page("https://example.com/docs", _RICH_HTML))
        self._assert_valid_decision(d)

    def test_enrich_has_rationale(self):
        model = {"transformer-attention": ["transformer", "attention", "self-attention"]}
        d = route_page(_make_page("https://example.com/attn", _ENRICH_HTML), model=model)
        self._assert_valid_decision(d)


# ---------------------------------------------------------------------------
# Tests: skip outcome
# ---------------------------------------------------------------------------


class TestSkipOutcome(unittest.TestCase):
    def test_stub_page_is_skipped(self):
        """Pages with very little visible text must be skipped."""
        d = route_page(_make_page("https://example.com/", _STUB_HTML))
        self.assertEqual("skip", d.outcome)

    def test_skip_sets_no_target_artifact(self):
        d = route_page(_make_page("https://example.com/", _STUB_HTML))
        self.assertIsNone(d.target_artifact_id)

    def test_skip_sets_no_page_title(self):
        d = route_page(_make_page("https://example.com/", _STUB_HTML))
        self.assertIsNone(d.page_title)

    def test_short_page_without_model_is_skipped(self):
        """Pages above stub threshold but below reference threshold → skip."""
        d = route_page(_make_page("https://example.com/short", _SHORT_HTML))
        self.assertEqual("skip", d.outcome)

    def test_skip_emits_nothing(self):
        """skip decision carries no artifact payload fields."""
        d = route_page(_make_page("https://example.com/", _STUB_HTML))
        self.assertIsNone(d.target_artifact_id)
        self.assertIsNone(d.page_title)
        self.assertIsNone(d.page_extract)


# ---------------------------------------------------------------------------
# Tests: reference outcome
# ---------------------------------------------------------------------------


class TestReferenceOutcome(unittest.TestCase):
    def test_rich_page_becomes_reference(self):
        d = route_page(_make_page("https://example.com/docs", _RICH_HTML))
        self.assertEqual("reference", d.outcome)

    def test_reference_has_page_title(self):
        d = route_page(_make_page("https://example.com/docs", _RICH_HTML))
        self.assertIsNotNone(d.page_title)
        self.assertIn("Deep Learning", d.page_title)

    def test_reference_has_page_extract(self):
        d = route_page(_make_page("https://example.com/docs", _RICH_HTML))
        self.assertIsNotNone(d.page_extract)
        self.assertGreater(len(d.page_extract), 0)

    def test_reference_has_no_target_artifact(self):
        d = route_page(_make_page("https://example.com/docs", _RICH_HTML))
        self.assertIsNone(d.target_artifact_id)


# ---------------------------------------------------------------------------
# Tests: enrich outcome
# ---------------------------------------------------------------------------


class TestEnrichOutcome(unittest.TestCase):
    def test_keyword_match_yields_enrich(self):
        model = {"transformer-attention": ["transformer", "attention", "self-attention"]}
        d = route_page(_make_page("https://example.com/attn", _ENRICH_HTML), model=model)
        self.assertEqual("enrich", d.outcome)

    def test_enrich_has_target_artifact_id(self):
        model = {"transformer-attention": ["transformer", "attention", "self-attention"]}
        d = route_page(_make_page("https://example.com/attn", _ENRICH_HTML), model=model)
        self.assertEqual("transformer-attention", d.target_artifact_id)

    def test_no_match_falls_back_to_reference(self):
        model = {"unrelated-topic": ["unicorn", "rainbow"]}
        d = route_page(_make_page("https://example.com/docs", _RICH_HTML), model=model)
        # No keywords match → falls through to reference (page is rich enough).
        self.assertEqual("reference", d.outcome)

    def test_enrich_has_no_page_title(self):
        model = {"transformer-attention": ["transformer", "attention", "self-attention"]}
        d = route_page(_make_page("https://example.com/attn", _ENRICH_HTML), model=model)
        self.assertIsNone(d.page_title)

    def test_empty_model_falls_back_to_reference(self):
        d = route_page(_make_page("https://example.com/docs", _RICH_HTML), model={})
        self.assertEqual("reference", d.outcome)

    def test_none_model_falls_back_to_reference(self):
        d = route_page(_make_page("https://example.com/docs", _RICH_HTML), model=None)
        self.assertEqual("reference", d.outcome)


# ---------------------------------------------------------------------------
# Tests: exactly one outcome
# ---------------------------------------------------------------------------


class TestExactlyOneOutcome(unittest.TestCase):
    def test_outcome_is_one_of_three(self):
        pages = [
            _make_page("https://example.com/stub", _STUB_HTML),
            _make_page("https://example.com/short", _SHORT_HTML),
            _make_page("https://example.com/rich", _RICH_HTML),
        ]
        for page in pages:
            d = route_page(page)
            self.assertIn(d.outcome, {"enrich", "reference", "skip"},
                          f"Unexpected outcome {d.outcome!r} for {page.url}")

    def test_decision_is_decision_instance(self):
        d = route_page(_make_page("https://example.com/docs", _RICH_HTML))
        self.assertIsInstance(d, Decision)


if __name__ == "__main__":
    unittest.main()
