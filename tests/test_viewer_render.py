#!/usr/bin/env python3
"""Tests for tools/viewer/render.py and commands/visualize.py.

Fixture wiki spans types, statuses (including needs-review and conflicted),
source tiers, both link forms, and a zero-source knowledge artifact.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixture helpers (mirror the pattern from test_viewer_extract.py)
# ---------------------------------------------------------------------------

def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _build_fixture(root: Path) -> None:
    """Populate *root* with a multi-status, multi-tier fixture wiki."""

    _write(root, "meta/source-registry.md", """\
---
artifact_type: source-registry
status: active
---

# Source Registry

| Source ID | Title | Tier | Status | Derived Path | Notes |
| --- | --- | --- | --- | --- | --- |
| paper-alpha | Alpha Paper | primary | active | - | primary |
| book-beta | Beta Book | secondary | active | - | secondary |
| web-gamma | Gamma Website | reference | active | - | reference |
""")

    # active + primary + has markdown link
    _write(root, "knowledge/alpha-note.md", """\
---
artifact_type: knowledge-note
status: active
title: Alpha Note
tags:
  - ml
description: A primary note about alpha findings.
sources:
  - paper-alpha
source_count: 1
updated: 2026-01-01
---

# Alpha Note

See [beta note](beta-note.md) and [[Beta Note]].
""")

    # verified + secondary
    _write(root, "knowledge/beta-note.md", """\
---
artifact_type: knowledge-note
status: verified
title: Beta Note
tags:
  - ml
sources:
  - book-beta
source_count: 1
updated: 2026-01-02
---

# Beta Note

See also [[Alpha Note]].
""")

    # needs-review + reference tier
    _write(root, "knowledge/review-note.md", """\
---
artifact_type: knowledge-note
status: needs-review
title: Needs Review Note
description: Needs review — uncertain provenance.
sources:
  - web-gamma
source_count: 1
updated: 2026-01-03
---

# Needs Review Note

This note needs review.
""")

    # conflicted + primary tier
    _write(root, "knowledge/conflicted-note.md", """\
---
artifact_type: knowledge-note
status: conflicted
title: Conflicted Note
description: Conflicting sources exist.
sources:
  - paper-alpha
source_count: 1
updated: 2026-01-04
---

# Conflicted Note

Conflicting information here.
""")

    # zero-source knowledge-note (should be flagged)
    _write(root, "knowledge/zero-source-note.md", """\
---
artifact_type: knowledge-note
status: draft
title: Zero Source Note
updated: 2026-01-05
---

# Zero Source Note

No sources whatsoever.
""")

    # decision artifact with description + reference tier
    _write(root, "decisions/gamma-decision.md", """\
---
artifact_type: decision
status: draft
title: Gamma Decision
description: A draft decision.
sources:
  - web-gamma
source_count: 1
updated: 2026-01-06
---

# Gamma Decision

References [[Alpha Note]].
""")


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

def _import_render():
    try:
        from tools.viewer.render import render_html, render_bundle, _build_graph_data
        return render_html, render_bundle, _build_graph_data
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools.viewer.render import render_html, render_bundle, _build_graph_data
        return render_html, render_bundle, _build_graph_data


def _import_extract():
    try:
        from tools.viewer.extract import build_graph
        return build_graph
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools.viewer.extract import build_graph
        return build_graph


def _build_fixture_graph(root: Path):
    build_graph = _import_extract()
    return build_graph(root)


# ---------------------------------------------------------------------------
# Test: embedded graph data correctness
# ---------------------------------------------------------------------------

class TestGraphDataEmbedded(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        _build_fixture(self.root)
        self.graph = _build_fixture_graph(self.root)
        _, _, self.build_graph_data = _import_render()
        self.data = self.build_graph_data(self.graph)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _node(self, title: str) -> dict:
        for n in self.data["nodes"]:
            if n["title"] == title:
                return n
        self.fail(f"Node with title={title!r} not found in embedded data")

    # ---- Status appears in embedded data ----

    def test_active_status_in_embedded_data(self):
        n = self._node("Alpha Note")
        self.assertEqual("active", n["status"])

    def test_verified_status_in_embedded_data(self):
        n = self._node("Beta Note")
        self.assertEqual("verified", n["status"])

    def test_needs_review_status_in_embedded_data(self):
        n = self._node("Needs Review Note")
        self.assertEqual("needs-review", n["status"])

    def test_conflicted_status_in_embedded_data(self):
        n = self._node("Conflicted Note")
        self.assertEqual("conflicted", n["status"])

    def test_draft_status_in_embedded_data(self):
        n = self._node("Zero Source Note")
        self.assertEqual("draft", n["status"])

    # ---- source_tier in embedded data ----

    def test_primary_tier_in_embedded_data(self):
        n = self._node("Alpha Note")
        self.assertEqual("primary", n["source_tier"])

    def test_secondary_tier_in_embedded_data(self):
        n = self._node("Beta Note")
        self.assertEqual("secondary", n["source_tier"])

    def test_reference_tier_in_embedded_data(self):
        n = self._node("Needs Review Note")
        self.assertEqual("reference", n["source_tier"])

    def test_zero_source_tier_in_embedded_data(self):
        n = self._node("Zero Source Note")
        self.assertEqual("zero-source", n["source_tier"])

    # ---- source_count and sources in embedded data ----

    def test_source_count_in_embedded_data(self):
        n = self._node("Alpha Note")
        self.assertEqual(1, n["source_count"])

    def test_sources_list_in_embedded_data(self):
        n = self._node("Alpha Note")
        self.assertIn("paper-alpha", n["sources"])

    def test_zero_source_count(self):
        n = self._node("Zero Source Note")
        self.assertEqual(0, n["source_count"])
        self.assertEqual([], n["sources"])

    # ---- zero_source flag ----

    def test_zero_source_flag_true_for_zero_source_note(self):
        n = self._node("Zero Source Note")
        self.assertTrue(n["zero_source"])

    def test_zero_source_flag_false_for_sourced_note(self):
        n = self._node("Alpha Note")
        self.assertFalse(n["zero_source"])

    # ---- attention flag for needs-review and conflicted ----

    def test_needs_review_attention_flag(self):
        n = self._node("Needs Review Note")
        self.assertTrue(n["attention"])

    def test_conflicted_attention_flag(self):
        n = self._node("Conflicted Note")
        self.assertTrue(n["attention"])

    def test_active_no_attention_flag(self):
        n = self._node("Alpha Note")
        self.assertFalse(n["attention"])

    # ---- description surfaced ----

    def test_description_in_embedded_data(self):
        n = self._node("Alpha Note")
        self.assertEqual("A primary note about alpha findings.", n["description"])

    def test_description_empty_string_when_absent(self):
        n = self._node("Beta Note")
        self.assertEqual("", n["description"])

    # ---- citations / backlinks in detail data ----

    def test_backlinks_populated_for_alpha(self):
        # beta-note, review-note, conflicted-note, zero-source-note, gamma-decision
        # all wikilink or markdownlink to alpha. At minimum beta links back.
        n = self._node("Alpha Note")
        self.assertIsInstance(n["backlinks"], list)

    def test_edges_populated(self):
        n = self._node("Alpha Note")
        self.assertIsInstance(n["edges"], list)
        self.assertGreater(len(n["edges"]), 0)

    # ---- stats fields ----

    def test_node_count_positive(self):
        self.assertGreater(self.data["node_count"], 0)

    def test_edge_count_non_negative(self):
        self.assertGreaterEqual(self.data["edge_count"], 0)

    def test_status_counts_keys(self):
        sc = self.data["status_counts"]
        self.assertIn("active", sc)
        self.assertIn("needs-review", sc)
        self.assertIn("conflicted", sc)

    def test_tier_counts_keys(self):
        tc = self.data["tier_counts"]
        self.assertIn("primary", tc)
        self.assertIn("zero-source", tc)

    def test_warnings_mention_zero_source(self):
        w = " ".join(self.data["warnings"])
        self.assertIn("zero-source", w.lower())

    def test_warnings_mention_attention(self):
        w = " ".join(self.data["warnings"])
        self.assertTrue(
            "needs-review" in w or "conflicted" in w,
            "Expected attention warning in: " + w,
        )


# ---------------------------------------------------------------------------
# Test: HTML output properties
# ---------------------------------------------------------------------------

class TestRenderHTML(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        _build_fixture(self.root)
        self.graph = _build_fixture_graph(self.root)
        self.render_html, _, self.build_graph_data = _import_render()
        self.html = self.render_html(self.graph)

    def tearDown(self):
        self._tmpdir.cleanup()

    # ---- No external network requests ----

    def test_no_external_http_in_src_attributes(self):
        # Match src="http..." or href="http..." pointing outside
        matches = re.findall(r'(?:src|href)=["\']https?://', self.html)
        self.assertEqual([], matches, "Found external network refs in src/href: " + str(matches))

    def test_no_external_script_tags(self):
        # <script src="..."> with external URL
        matches = re.findall(r'<script[^>]+src=["\']https?://', self.html)
        self.assertEqual([], matches)

    def test_no_external_link_tags(self):
        matches = re.findall(r'<link[^>]+href=["\']https?://', self.html)
        self.assertEqual([], matches)

    def test_no_external_font_imports(self):
        matches = re.findall(r'@import\s+["\']https?://', self.html)
        self.assertEqual([], matches)

    def test_no_cdn_references(self):
        # Common CDNs that would require network
        for cdn in ("cdn.jsdelivr", "cdnjs.cloudflare", "unpkg.com", "fonts.googleapis"):
            self.assertNotIn(cdn, self.html, f"Found CDN reference: {cdn}")

    # ---- Styling hooks present ----

    def test_status_active_color_in_html(self):
        # Colour for 'active' status is encoded in the JS object literal
        self.assertIn("4caf50", self.html)  # #4caf50

    def test_status_needs_review_color_in_html(self):
        self.assertIn("ff9800", self.html)  # #ff9800

    def test_status_conflicted_color_in_html(self):
        self.assertIn("f44336", self.html)  # #f44336

    def test_zero_source_color_in_html(self):
        self.assertIn("ff5722", self.html)  # #ff5722 for zero-source

    def test_tier_primary_color_in_html(self):
        self.assertIn("7c4dff", self.html)

    # ---- Embedded JSON parseable ----

    def test_embedded_graph_data_parseable(self):
        match = re.search(r'window\.GRAPH_DATA\s*=\s*(\{.*?\});', self.html, re.DOTALL)
        self.assertIsNotNone(match, "GRAPH_DATA assignment not found in HTML")
        data = json.loads(match.group(1))
        self.assertIn("nodes", data)
        self.assertIn("links", data)
        self.assertIn("node_count", data)
        self.assertIn("edge_count", data)
        self.assertIn("status_counts", data)
        self.assertIn("tier_counts", data)
        self.assertIn("warnings", data)

    def test_embedded_data_nodes_have_required_keys(self):
        match = re.search(r'window\.GRAPH_DATA\s*=\s*(\{.*?\});', self.html, re.DOTALL)
        data = json.loads(match.group(1))
        required_keys = {"id", "title", "status", "source_tier", "source_count",
                         "sources", "zero_source", "attention", "backlinks", "edges"}
        for node in data["nodes"]:
            for k in required_keys:
                self.assertIn(k, node, f"Key {k!r} missing from node {node.get('id')!r}")

    # ---- needs-review / conflicted are marked in embedded data ----

    def test_needs_review_marked_in_embedded_data(self):
        match = re.search(r'window\.GRAPH_DATA\s*=\s*(\{.*?\});', self.html, re.DOTALL)
        data = json.loads(match.group(1))
        review_nodes = [n for n in data["nodes"] if n["status"] == "needs-review"]
        self.assertGreater(len(review_nodes), 0)
        for n in review_nodes:
            self.assertTrue(n["attention"], f"needs-review node {n['id']} not marked as attention")

    def test_conflicted_marked_in_embedded_data(self):
        match = re.search(r'window\.GRAPH_DATA\s*=\s*(\{.*?\});', self.html, re.DOTALL)
        data = json.loads(match.group(1))
        conflicted_nodes = [n for n in data["nodes"] if n["status"] == "conflicted"]
        self.assertGreater(len(conflicted_nodes), 0)
        for n in conflicted_nodes:
            self.assertTrue(n["attention"], f"conflicted node {n['id']} not marked as attention")

    # ---- zero-source artifact is flagged ----

    def test_zero_source_flagged_in_embedded_data(self):
        match = re.search(r'window\.GRAPH_DATA\s*=\s*(\{.*?\});', self.html, re.DOTALL)
        data = json.loads(match.group(1))
        zs_nodes = [n for n in data["nodes"] if n["title"] == "Zero Source Note"]
        self.assertGreater(len(zs_nodes), 0)
        self.assertTrue(zs_nodes[0]["zero_source"])

    # ---- description surfaced ----

    def test_description_in_embedded_data_from_html(self):
        match = re.search(r'window\.GRAPH_DATA\s*=\s*(\{.*?\});', self.html, re.DOTALL)
        data = json.loads(match.group(1))
        alpha = next((n for n in data["nodes"] if n["title"] == "Alpha Note"), None)
        self.assertIsNotNone(alpha)
        self.assertEqual("A primary note about alpha findings.", alpha["description"])

    # ---- Structural HTML checks ----

    def test_html_has_canvas_element(self):
        self.assertIn('<canvas id="graph-canvas"', self.html)

    def test_html_has_detail_pane(self):
        self.assertIn('id="detail-pane"', self.html)

    def test_html_has_search_control(self):
        self.assertIn('id="search"', self.html)

    def test_html_has_legend(self):
        self.assertIn('id="legend"', self.html)

    def test_html_has_type_filter(self):
        self.assertIn('id="type-filter"', self.html)


# ---------------------------------------------------------------------------
# Test: determinism
# ---------------------------------------------------------------------------

class TestDeterminism(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        _build_fixture(self.root)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_two_renders_are_identical(self):
        render_html = _import_render()[0]
        build_graph = _import_extract()
        g1 = build_graph(self.root)
        g2 = build_graph(self.root)
        h1 = render_html(g1)
        h2 = render_html(g2)
        self.assertEqual(h1, h2)

    def test_embedded_data_node_order_is_stable(self):
        render_html = _import_render()[0]
        build_graph = _import_extract()
        html1 = render_html(build_graph(self.root))
        html2 = render_html(build_graph(self.root))
        m1 = re.search(r'window\.GRAPH_DATA\s*=\s*(\{.*?\});', html1, re.DOTALL)
        m2 = re.search(r'window\.GRAPH_DATA\s*=\s*(\{.*?\});', html2, re.DOTALL)
        d1 = json.loads(m1.group(1))
        d2 = json.loads(m2.group(1))
        ids1 = [n["id"] for n in d1["nodes"]]
        ids2 = [n["id"] for n in d2["nodes"]]
        self.assertEqual(ids1, ids2)


# ---------------------------------------------------------------------------
# Test: render_bundle
# ---------------------------------------------------------------------------

class TestRenderBundle(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        _build_fixture(self.root)
        self.graph = _build_fixture_graph(self.root)
        _, self.render_bundle, _ = _import_render()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_bundle_creates_html_file(self):
        out = Path(self._tmpdir.name) / "bundle"
        written = self.render_bundle(self.graph, out)
        self.assertTrue(written["html"].exists())

    def test_bundle_creates_data_json(self):
        out = Path(self._tmpdir.name) / "bundle2"
        written = self.render_bundle(self.graph, out)
        self.assertTrue(written["data"].exists())

    def test_bundle_data_json_parseable(self):
        out = Path(self._tmpdir.name) / "bundle3"
        written = self.render_bundle(self.graph, out)
        data = json.loads(written["data"].read_text(encoding="utf-8"))
        self.assertIn("nodes", data)
        self.assertIn("links", data)


# ---------------------------------------------------------------------------
# Test: visualize CLI command
# ---------------------------------------------------------------------------

class TestVisualizeCommand(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        _build_fixture(self.root)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _get_app(self):
        from typer.testing import CliRunner
        import typer
        import importlib
        import llm_wiki_wizard.commands as cmds
        importlib.invalidate_caches()
        fresh_app = typer.Typer()
        from llm_wiki_wizard.commands import register_all
        register_all(fresh_app)
        return fresh_app, CliRunner()

    def test_visualize_command_is_autodiscovered(self):
        """visualize should appear in app commands without editing cli.py."""
        from typer.testing import CliRunner
        from llm_wiki_wizard.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        self.assertEqual(0, result.exit_code, result.output)
        # Check the command is registered
        names = {info.name or info.callback.__name__ for info in app.registered_commands}
        self.assertIn("visualize", names)

    def test_visualize_produces_output_for_valid_wiki(self):
        app, runner = self._get_app()
        out_dir = Path(self._tmpdir.name) / "out"
        result = runner.invoke(app, ["visualize", str(self.root), "--output", str(out_dir)])
        self.assertEqual(0, result.exit_code, result.output)
        html_file = out_dir / "index.html"
        self.assertTrue(html_file.exists(), f"index.html not created in {out_dir}")

    def test_visualize_json_output_has_required_keys(self):
        app, runner = self._get_app()
        out_dir = Path(self._tmpdir.name) / "out_json"
        result = runner.invoke(app, ["visualize", str(self.root), "--output", str(out_dir), "--json"])
        self.assertEqual(0, result.exit_code, result.output)
        payload = json.loads(result.output)
        for key in ("output", "data_output", "node_count", "edge_count",
                    "status_counts", "tier_counts", "warnings"):
            self.assertIn(key, payload, f"Key {key!r} missing from --json output")

    def test_visualize_json_node_count_positive(self):
        app, runner = self._get_app()
        out_dir = Path(self._tmpdir.name) / "out_count"
        result = runner.invoke(app, ["visualize", str(self.root), "--output", str(out_dir), "--json"])
        self.assertEqual(0, result.exit_code, result.output)
        payload = json.loads(result.output)
        self.assertGreater(payload["node_count"], 0)

    def test_visualize_non_wiki_target_exits_nonzero(self):
        app, runner = self._get_app()
        non_wiki = Path(self._tmpdir.name) / "empty_dir"
        non_wiki.mkdir()
        result = runner.invoke(app, ["visualize", str(non_wiki)])
        self.assertNotEqual(0, result.exit_code,
                            "Expected non-zero exit for non-wiki target, got 0")

    def test_visualize_nonexistent_target_exits_nonzero(self):
        app, runner = self._get_app()
        non_existent = Path(self._tmpdir.name) / "does_not_exist"
        result = runner.invoke(app, ["visualize", str(non_existent)])
        self.assertNotEqual(0, result.exit_code)

    def test_visualize_json_warns_zero_source(self):
        app, runner = self._get_app()
        out_dir = Path(self._tmpdir.name) / "out_warn"
        result = runner.invoke(app, ["visualize", str(self.root), "--output", str(out_dir), "--json"])
        self.assertEqual(0, result.exit_code, result.output)
        payload = json.loads(result.output)
        w = " ".join(payload["warnings"])
        self.assertIn("zero-source", w.lower())

    def test_visualize_output_html_has_no_external_refs(self):
        """The HTML written by the command must not reference external resources."""
        app, runner = self._get_app()
        out_dir = Path(self._tmpdir.name) / "out_noext"
        runner.invoke(app, ["visualize", str(self.root), "--output", str(out_dir)])
        html = (out_dir / "index.html").read_text(encoding="utf-8")
        for cdn in ("cdn.jsdelivr", "cdnjs.cloudflare", "unpkg.com", "fonts.googleapis"):
            self.assertNotIn(cdn, html, f"Found CDN reference: {cdn}")
        matches = re.findall(r'(?:src|href)=["\']https?://', html)
        self.assertEqual([], matches, "External src/href in HTML: " + str(matches))


if __name__ == "__main__":
    unittest.main()
