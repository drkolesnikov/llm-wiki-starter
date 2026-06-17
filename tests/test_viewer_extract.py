#!/usr/bin/env python3
"""Tests for tools/viewer/extract.py — governance-aware graph extraction.

Fixture wiki spans multiple artifact types, statuses, source tiers, both
Markdown and wikilink forms, and a zero-source knowledge-note.
"""

import tempfile
import unittest
from pathlib import Path


def _write(root: Path, rel: str, content: str) -> Path:
    """Write *content* to *root/rel*, creating intermediate dirs."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _build_fixture(root: Path) -> None:
    """Populate *root* with a minimal multi-artifact fixture wiki."""

    # -- source-registry so tier resolution works --
    _write(root, "meta/source-registry.md", """\
---
artifact_type: source-registry
status: active
---

# Source Registry

| Source ID | Title | Tier | Status | Derived Path | Notes |
| --- | --- | --- | --- | --- | --- |
| paper-alpha | Alpha Paper | primary | active | - | key primary source |
| book-beta | Beta Book | secondary | active | - | secondary reference |
| web-gamma | Gamma Website | reference | active | - | background web source |
""")

    # -- knowledge-note with sources (primary tier) and a Markdown link --
    _write(root, "knowledge/alpha-note.md", """\
---
artifact_type: knowledge-note
status: active
title: Alpha Note
tags:
  - ml
  - research
description: A primary note about alpha findings.
sources:
  - paper-alpha
source_count: 1
linked_concepts:
  - "[[Beta Note]]"
updated: 2026-01-01
---

# Alpha Note

Body text with a [markdown link](beta-note.md) and [[Beta Note]] as a wikilink.
Also links to the [source registry](../meta/source-registry.md).
""")

    # -- knowledge-note with secondary source and only wikilinks --
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

See also [[Alpha Note]] for the primary perspective.
And [[Gamma Decision]] from decisions.
""")

    # -- decision artifact with reference-tier source --
    _write(root, "decisions/gamma-decision.md", """\
---
artifact_type: decision
status: draft
title: Gamma Decision
description: A draft decision referencing web source.
sources:
  - web-gamma
source_count: 1
updated: 2026-01-03
---

# Gamma Decision

This decision references [[Alpha Note]].
""")

    # -- knowledge-note with ZERO sources (should be flagged) --
    _write(root, "knowledge/zero-source-note.md", """\
---
artifact_type: knowledge-note
status: draft
title: Zero Source Note
updated: 2026-01-04
---

# Zero Source Note

No sources at all. Links to [[Alpha Note]].
""")

    # -- artifact with unknown status (not in ALLOWED_STATUSES) --
    _write(root, "knowledge/unknown-status-note.md", """\
---
artifact_type: knowledge-note
status: totally-made-up
title: Unknown Status Note
sources:
  - paper-alpha
source_count: 1
updated: 2026-01-05
---

# Unknown Status Note

Has an invalid status value.
""")

    # -- artifact with a broken internal Markdown link (unresolved) --
    _write(root, "knowledge/broken-link-note.md", """\
---
artifact_type: knowledge-note
status: active
title: Broken Link Note
sources:
  - paper-alpha
source_count: 1
updated: 2026-01-06
---

# Broken Link Note

Points to [a missing file](does-not-exist.md) which should be unresolved.
Also has a [[NoSuchArticle]] wikilink.
""")


class TestBuildGraph(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        _build_fixture(self.root)

        # Import here so sys.path tricks in the module don't matter.
        import sys
        repo_root = Path(__file__).resolve().parents[1]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        from tools.viewer.extract import build_graph, UNRESOLVED_MARKER, ZERO_SOURCE_FLAG, UNKNOWN_VALUE
        self.build_graph = build_graph
        self.UNRESOLVED_MARKER = UNRESOLVED_MARKER
        self.ZERO_SOURCE_FLAG = ZERO_SOURCE_FLAG
        self.UNKNOWN_VALUE = UNKNOWN_VALUE

        self.graph = build_graph(self.root)

    def tearDown(self):
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # Helper shortcuts
    # ------------------------------------------------------------------

    def _node(self, rel_path: str):
        return self.graph.nodes.get(rel_path)

    # ------------------------------------------------------------------
    # 1. Expected nodes exist
    # ------------------------------------------------------------------

    def test_expected_nodes_present(self):
        expected = [
            "knowledge/alpha-note.md",
            "knowledge/beta-note.md",
            "decisions/gamma-decision.md",
            "knowledge/zero-source-note.md",
            "knowledge/unknown-status-note.md",
            "knowledge/broken-link-note.md",
            "meta/source-registry.md",
        ]
        for rel_path in expected:
            with self.subTest(rel_path=rel_path):
                self.assertIn(rel_path, self.graph.nodes,
                              f"Expected node {rel_path!r} missing from graph")

    # ------------------------------------------------------------------
    # 2. Node fields: status / tier / sources / source_count / description / body
    # ------------------------------------------------------------------

    def test_alpha_note_fields(self):
        node = self._node("knowledge/alpha-note.md")
        self.assertIsNotNone(node)
        self.assertEqual(node.artifact_type, "knowledge-note")
        self.assertEqual(node.title, "Alpha Note")
        self.assertEqual(node.status, "active")
        self.assertIn("ml", node.tags)
        self.assertEqual(node.description, "A primary note about alpha findings.")
        self.assertEqual(node.sources, ["paper-alpha"])
        self.assertEqual(node.source_count, 1)
        self.assertEqual(node.source_tier, "primary")
        self.assertIn("Body text", node.body)

    def test_beta_note_fields(self):
        node = self._node("knowledge/beta-note.md")
        self.assertIsNotNone(node)
        self.assertEqual(node.status, "verified")
        self.assertEqual(node.source_tier, "secondary")
        self.assertIsNone(node.description)   # not present in fixture

    def test_gamma_decision_fields(self):
        node = self._node("decisions/gamma-decision.md")
        self.assertIsNotNone(node)
        self.assertEqual(node.artifact_type, "decision")
        self.assertEqual(node.status, "draft")
        self.assertEqual(node.source_tier, "reference")
        self.assertEqual(node.description, "A draft decision referencing web source.")

    # ------------------------------------------------------------------
    # 3. Unknown status is flagged as "unknown"
    # ------------------------------------------------------------------

    def test_unknown_status_flagged(self):
        node = self._node("knowledge/unknown-status-note.md")
        self.assertIsNotNone(node)
        self.assertEqual(node.status, self.UNKNOWN_VALUE,
                         "Status outside closed vocab should be 'unknown'")

    # ------------------------------------------------------------------
    # 4. Zero-source knowledge-note flagged
    # ------------------------------------------------------------------

    def test_zero_source_knowledge_note_flagged(self):
        node = self._node("knowledge/zero-source-note.md")
        self.assertIsNotNone(node)
        self.assertEqual(node.sources, [])
        self.assertEqual(node.source_count, 0)
        self.assertEqual(node.source_tier, self.ZERO_SOURCE_FLAG,
                         "knowledge-note with zero sources should carry ZERO_SOURCE_FLAG")

    # ------------------------------------------------------------------
    # 5. Edges — Markdown links produce edges of kind "markdown"
    # ------------------------------------------------------------------

    def test_markdown_edge_alpha_to_beta(self):
        node = self._node("knowledge/alpha-note.md")
        self.assertIsNotNone(node)
        md_edges = [e for e in node.edges if e.kind == "markdown" and e.resolved]
        target_ids = [e.target_id for e in md_edges]
        self.assertIn("knowledge/beta-note.md", target_ids,
                      "Markdown link to beta-note.md should produce resolved edge")

    def test_markdown_edge_to_source_registry(self):
        node = self._node("knowledge/alpha-note.md")
        self.assertIsNotNone(node)
        md_edges = [e for e in node.edges if e.kind == "markdown" and e.resolved]
        target_ids = [e.target_id for e in md_edges]
        self.assertIn("meta/source-registry.md", target_ids,
                      "Markdown link to source-registry.md should be resolved")

    # ------------------------------------------------------------------
    # 6. Edges — wikilinks produce edges of kind "wikilink"
    # ------------------------------------------------------------------

    def test_wikilink_edge_beta_to_alpha(self):
        node = self._node("knowledge/beta-note.md")
        self.assertIsNotNone(node)
        wiki_edges = [e for e in node.edges if e.kind == "wikilink" and e.resolved]
        target_ids = [e.target_id for e in wiki_edges]
        self.assertIn("knowledge/alpha-note.md", target_ids,
                      "[[Alpha Note]] wikilink should resolve to alpha-note.md")

    def test_wikilink_edge_beta_to_gamma(self):
        node = self._node("knowledge/beta-note.md")
        self.assertIsNotNone(node)
        wiki_edges = [e for e in node.edges if e.kind == "wikilink" and e.resolved]
        target_ids = [e.target_id for e in wiki_edges]
        self.assertIn("decisions/gamma-decision.md", target_ids,
                      "[[Gamma Decision]] wikilink should resolve to gamma-decision.md")

    def test_frontmatter_linked_concepts_produce_wikilink_edges(self):
        """linked_concepts in frontmatter should also generate wikilink edges."""
        node = self._node("knowledge/alpha-note.md")
        self.assertIsNotNone(node)
        wiki_edges = [e for e in node.edges if e.kind == "wikilink"]
        # "[[Beta Note]]" from linked_concepts should appear.
        self.assertTrue(
            any("beta-note" in e.target_id for e in wiki_edges if e.resolved),
            "linked_concepts wikilink should produce a wikilink edge to beta-note",
        )

    # ------------------------------------------------------------------
    # 7. Backlinks — inversion of forward edges
    # ------------------------------------------------------------------

    def test_backlinks_invert_forward_edges(self):
        """beta-note should carry a backlink from alpha-note (markdown link)."""
        beta = self._node("knowledge/beta-note.md")
        self.assertIsNotNone(beta)
        backlink_sources = [e.source_id for e in beta.backlinks]
        self.assertIn("knowledge/alpha-note.md", backlink_sources,
                      "alpha-note should appear in beta-note's backlinks")

    def test_alpha_note_backlinks_include_beta(self):
        """alpha-note is linked by beta-note (wikilink) so should have a backlink."""
        alpha = self._node("knowledge/alpha-note.md")
        self.assertIsNotNone(alpha)
        backlink_sources = [e.source_id for e in alpha.backlinks]
        self.assertIn("knowledge/beta-note.md", backlink_sources,
                      "beta-note wikilink to alpha-note should appear as a backlink")

    def test_backlinks_count_consistent(self):
        """Every backlink edge's source_id should point to an existing node."""
        for nid, node in self.graph.nodes.items():
            for bl in node.backlinks:
                self.assertIn(bl.source_id, self.graph.nodes,
                              f"Backlink source {bl.source_id!r} not in graph nodes")

    # ------------------------------------------------------------------
    # 8. Unresolved link handling — never crashes, uses UNRESOLVED_MARKER
    # ------------------------------------------------------------------

    def test_unresolved_markdown_link_flagged(self):
        node = self._node("knowledge/broken-link-note.md")
        self.assertIsNotNone(node)
        unresolved_md = [
            e for e in node.edges
            if e.kind == "markdown" and not e.resolved
        ]
        self.assertTrue(
            len(unresolved_md) >= 1,
            "Broken internal Markdown link should produce an unresolved edge",
        )
        self.assertEqual(unresolved_md[0].target_id, self.UNRESOLVED_MARKER)

    def test_unresolved_wikilink_flagged(self):
        node = self._node("knowledge/broken-link-note.md")
        self.assertIsNotNone(node)
        unresolved_wiki = [
            e for e in node.edges
            if e.kind == "wikilink" and not e.resolved
        ]
        self.assertTrue(
            len(unresolved_wiki) >= 1,
            "[[NoSuchArticle]] wikilink should produce an unresolved edge",
        )
        self.assertEqual(unresolved_wiki[0].target_id, self.UNRESOLVED_MARKER)

    def test_unresolved_links_not_in_backlinks(self):
        """Unresolved edges must NOT appear in any node's backlinks."""
        for nid, node in self.graph.nodes.items():
            for bl in node.backlinks:
                self.assertNotEqual(
                    bl.target_id, self.UNRESOLVED_MARKER,
                    f"Unresolved edge found in backlinks of {nid!r}",
                )

    # ------------------------------------------------------------------
    # 9. No crash on missing fields
    # ------------------------------------------------------------------

    def test_no_crash_builds_graph(self):
        """build_graph must not raise for any fixture artifact."""
        # If we reach this point, setUp() did not crash.
        self.assertIsNotNone(self.graph)
        self.assertGreater(len(self.graph.nodes), 0)

    def test_node_without_optional_fields_is_safe(self):
        """zero-source-note has no tags, no description — node should still exist."""
        node = self._node("knowledge/zero-source-note.md")
        self.assertIsNotNone(node)
        self.assertEqual(node.tags, [])
        self.assertIsNone(node.description)

    # ------------------------------------------------------------------
    # 10. Edge kind coverage
    # ------------------------------------------------------------------

    def test_both_edge_kinds_present_in_graph(self):
        all_kinds = {e.kind for node in self.graph.nodes.values() for e in node.edges}
        self.assertIn("markdown", all_kinds, "No markdown edges found")
        self.assertIn("wikilink", all_kinds, "No wikilink edges found")

    # ------------------------------------------------------------------
    # 11. GraphModel root path stored correctly
    # ------------------------------------------------------------------

    def test_graph_root_matches_fixture(self):
        self.assertEqual(self.graph.root.resolve(), self.root.resolve())


if __name__ == "__main__":
    unittest.main()
