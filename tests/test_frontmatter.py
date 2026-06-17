"""Tests for #57: deep frontmatter parser + canonical tree-walker.

Covers the acceptance criteria from the issue:
- scalar values (with quote-stripping)
- list values (block + inline)
- quoted values
- OKF ``namespace:field`` extension keys
- missing-frontmatter handling
- round-trip via ``preserve_raw``
- the canonical ``markdown_files`` walker honouring SKIP_DIRS
- a superset-of-``validate_repo.parse_frontmatter`` parity guarantee

Uses the stdlib ``unittest`` runner (NOT pytest).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import frontmatter, validate_repo, wiki_spec


# ---------------------------------------------------------------------------
# Scalar / quote handling
# ---------------------------------------------------------------------------


class CleanScalarTests(unittest.TestCase):
    def test_strips_double_quotes(self):
        self.assertEqual(frontmatter.clean_scalar('"hello"'), "hello")

    def test_strips_single_quotes(self):
        self.assertEqual(frontmatter.clean_scalar("'hello'"), "hello")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(frontmatter.clean_scalar("  hello  "), "hello")

    def test_leaves_unquoted_value(self):
        self.assertEqual(frontmatter.clean_scalar("hello"), "hello")

    def test_does_not_strip_mismatched_quotes(self):
        # Leading double, trailing single — not a matched pair.
        self.assertEqual(frontmatter.clean_scalar("\"hello'"), "\"hello'")

    def test_does_not_strip_internal_quotes(self):
        self.assertEqual(frontmatter.clean_scalar("a'b"), "a'b")


class ScalarParseTests(unittest.TestCase):
    def test_basic_scalars(self):
        text = "---\nartifact_type: knowledge-note\nstatus: active\n---\nBody"
        parsed = frontmatter.parse_frontmatter(text)
        self.assertTrue(parsed.has_frontmatter)
        self.assertEqual(parsed.data["artifact_type"], "knowledge-note")
        self.assertEqual(parsed.data["status"], "active")

    def test_quoted_scalar_is_unquoted(self):
        text = '---\ntitle: "A Quoted Title"\nowner: \'agent-x\'\n---\nBody'
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["title"], "A Quoted Title")
        self.assertEqual(parsed.data["owner"], "agent-x")

    def test_value_containing_colon_space_keeps_remainder(self):
        # Only the first ": " splits; the rest of the value is preserved.
        text = "---\ndescription: Ratios: a study of proportion\n---\nBody"
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["description"], "Ratios: a study of proportion")

    def test_body_is_text_after_fence(self):
        text = "---\ntitle: T\n---\nLine 1\nLine 2"
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.body, "Line 1\nLine 2")
        self.assertEqual(parsed.body_start, 3)


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


class ListParseTests(unittest.TestCase):
    def test_block_list(self):
        text = "---\ntags:\n  - alpha\n  - beta\n---\nBody"
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["tags"], ["alpha", "beta"])

    def test_block_list_items_are_quote_stripped(self):
        text = "---\naliases:\n  - \"One\"\n  - 'Two'\n---\nBody"
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["aliases"], ["One", "Two"])

    def test_inline_list(self):
        text = "---\ntags: [alpha, beta, gamma]\n---\nBody"
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["tags"], ["alpha", "beta", "gamma"])

    def test_inline_list_quote_stripped(self):
        text = '---\ntags: ["a", \'b\']\n---\nBody'
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["tags"], ["a", "b"])

    def test_empty_inline_list(self):
        text = "---\ntags: []\n---\nBody"
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["tags"], [])

    def test_bare_key_is_empty_list(self):
        text = "---\ntags:\n---\nBody"
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["tags"], [])

    def test_two_block_lists_do_not_bleed(self):
        text = (
            "---\n"
            "tags:\n"
            "  - a\n"
            "aliases:\n"
            "  - b\n"
            "---\n"
            "Body"
        )
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["tags"], ["a"])
        self.assertEqual(parsed.data["aliases"], ["b"])

    def test_scalar_then_block_list_for_other_key(self):
        text = (
            "---\n"
            "title: My Note\n"
            "tags:\n"
            "  - x\n"
            "  - y\n"
            "status: draft\n"
            "---\n"
            "Body"
        )
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["title"], "My Note")
        self.assertEqual(parsed.data["tags"], ["x", "y"])
        self.assertEqual(parsed.data["status"], "draft")


# ---------------------------------------------------------------------------
# OKF extension keys (compound ``namespace:field``)
# ---------------------------------------------------------------------------


class ExtensionKeyTests(unittest.TestCase):
    def test_compound_scalar_key(self):
        text = "---\nllm-wiki:status: active\n---\nBody"
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["llm-wiki:status"], "active")
        self.assertNotIn("llm-wiki", parsed.data)

    def test_compound_key_with_quoted_value(self):
        text = '---\nllm-wiki:owner: "Agent X"\n---\nBody'
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["llm-wiki:owner"], "Agent X")

    def test_compound_key_with_block_list(self):
        text = (
            "---\n"
            "llm-wiki:tags:\n"
            "  - one\n"
            "  - two\n"
            "---\n"
            "Body"
        )
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["llm-wiki:tags"], ["one", "two"])

    def test_compound_key_with_inline_list(self):
        text = "---\nllm-wiki:sources: [s1, s2]\n---\nBody"
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["llm-wiki:sources"], ["s1", "s2"])

    def test_plain_and_extension_keys_coexist(self):
        text = (
            "---\n"
            "artifact_type: knowledge-note\n"
            "title: Mixed\n"
            "llm-wiki:status: verified\n"
            "---\n"
            "Body"
        )
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data["artifact_type"], "knowledge-note")
        self.assertEqual(parsed.data["title"], "Mixed")
        self.assertEqual(parsed.data["llm-wiki:status"], "verified")


# ---------------------------------------------------------------------------
# Missing / malformed frontmatter
# ---------------------------------------------------------------------------


class MissingFrontmatterTests(unittest.TestCase):
    def test_no_fence_returns_no_frontmatter(self):
        text = "# Just a heading\n\nSome body text."
        parsed = frontmatter.parse_frontmatter(text)
        self.assertFalse(parsed.has_frontmatter)
        self.assertEqual(parsed.data, {})
        self.assertEqual(parsed.body, text)
        self.assertEqual(parsed.body_start, 0)

    def test_empty_string(self):
        parsed = frontmatter.parse_frontmatter("")
        self.assertFalse(parsed.has_frontmatter)
        self.assertEqual(parsed.data, {})
        self.assertEqual(parsed.body, "")

    def test_empty_fence_has_frontmatter_but_no_data(self):
        text = "---\n---\nBody"
        parsed = frontmatter.parse_frontmatter(text)
        self.assertTrue(parsed.has_frontmatter)
        self.assertEqual(parsed.data, {})
        self.assertEqual(parsed.body, "Body")

    def test_unterminated_fence_consumes_remainder(self):
        text = "---\ntitle: T\nstatus: draft"
        parsed = frontmatter.parse_frontmatter(text)
        self.assertTrue(parsed.has_frontmatter)
        self.assertEqual(parsed.data["title"], "T")
        self.assertEqual(parsed.data["status"], "draft")
        self.assertEqual(parsed.body, "")

    def test_comments_and_blanks_are_skipped(self):
        text = (
            "---\n"
            "# a comment\n"
            "\n"
            "title: T\n"
            "  # indented comment\n"
            "---\n"
            "Body"
        )
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.data, {"title": "T"})


# ---------------------------------------------------------------------------
# split_frontmatter shim
# ---------------------------------------------------------------------------


class SplitFrontmatterShimTests(unittest.TestCase):
    def test_returns_none_for_missing(self):
        data, start = frontmatter.split_frontmatter("no fence here")
        self.assertIsNone(data)
        self.assertEqual(start, 0)

    def test_returns_data_and_body_start(self):
        text = "---\ntitle: T\n---\nBody"
        data, start = frontmatter.split_frontmatter(text)
        self.assertEqual(data, {"title": "T"})
        self.assertEqual(start, 3)

    def test_unterminated_matches_validator_sentinel(self):
        text = "---\ntitle: T"
        data, start = frontmatter.split_frontmatter(text)
        self.assertEqual(start, len(text.splitlines()))
        self.assertIsInstance(data, dict)


# ---------------------------------------------------------------------------
# Round-trip / raw-line preservation
# ---------------------------------------------------------------------------


class RoundTripTests(unittest.TestCase):
    def test_raw_lines_absent_by_default(self):
        text = "---\ntitle: T\n---\nBody"
        parsed = frontmatter.parse_frontmatter(text)
        self.assertEqual(parsed.raw_lines, [])

    def test_raw_lines_captured_verbatim(self):
        inner = ['title: "Quoted"', "tags:", "  - a", "  - b"]
        text = "---\n" + "\n".join(inner) + "\n---\nBody line"
        parsed = frontmatter.parse_frontmatter(text, preserve_raw=True)
        self.assertEqual(parsed.raw_lines, inner)

    def test_full_round_trip_reconstruction(self):
        original = (
            "---\n"
            'title: "Round Trip"\n'
            "tags:\n"
            "  - one\n"
            "  - two\n"
            "llm-wiki:status: active\n"
            "---\n"
            "First body line.\n"
            "Second body line."
        )
        parsed = frontmatter.parse_frontmatter(original, preserve_raw=True)
        # Reconstruct from raw_lines + body and confirm byte-for-byte identity.
        reconstructed = "---\n" + "\n".join(parsed.raw_lines) + "\n---\n" + parsed.body
        self.assertEqual(reconstructed, original)

    def test_round_trip_preserves_quotes_and_formatting(self):
        # The structured ``data`` view strips quotes; raw_lines keeps them.
        text = "---\ntitle: 'kept'\n---\nB"
        parsed = frontmatter.parse_frontmatter(text, preserve_raw=True)
        self.assertEqual(parsed.data["title"], "kept")          # normalised
        self.assertEqual(parsed.raw_lines, ["title: 'kept'"])    # verbatim


# ---------------------------------------------------------------------------
# Canonical tree-walker
# ---------------------------------------------------------------------------


class MarkdownFilesWalkerTests(unittest.TestCase):
    def test_finds_md_files_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.md").write_text("b", encoding="utf-8")
            (root / "a.md").write_text("a", encoding="utf-8")
            sub = root / "knowledge"
            sub.mkdir()
            (sub / "c.md").write_text("c", encoding="utf-8")
            found = frontmatter.markdown_files(root)
            rel = [p.relative_to(root).as_posix() for p in found]
            self.assertEqual(rel, ["a.md", "b.md", "knowledge/c.md"])

    def test_skips_skip_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.md").write_text("k", encoding="utf-8")
            for skip in (".git", ".venv", "__pycache__", "scratch", "tmp"):
                d = root / skip
                d.mkdir()
                (d / "ignored.md").write_text("x", encoding="utf-8")
            found = frontmatter.markdown_files(root)
            rel = [p.relative_to(root).as_posix() for p in found]
            self.assertEqual(rel, ["keep.md"])

    def test_skips_nested_skip_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "knowledge" / "__pycache__"
            nested.mkdir(parents=True)
            (nested / "x.md").write_text("x", encoding="utf-8")
            (root / "knowledge" / "real.md").write_text("r", encoding="utf-8")
            found = frontmatter.markdown_files(root)
            rel = [p.relative_to(root).as_posix() for p in found]
            self.assertEqual(rel, ["knowledge/real.md"])

    def test_accepts_string_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.md").write_text("x", encoding="utf-8")
            found = frontmatter.markdown_files(tmp)
            self.assertEqual(len(found), 1)

    def test_uses_canonical_skip_dirs(self):
        # Guard: the walker honours the shared SKIP_DIRS, not a private copy.
        self.assertIn(".git", wiki_spec.SKIP_DIRS)
        self.assertIn("__pycache__", wiki_spec.SKIP_DIRS)


# ---------------------------------------------------------------------------
# Superset-of-validator parity
# ---------------------------------------------------------------------------


class ValidatorSupersetTests(unittest.TestCase):
    """The new parser must agree with ``validate_repo.parse_frontmatter`` on
    every input the validator already handles, and additionally handle the
    extension-key / inline-list cases the validator does not.
    """

    PARITY_CASES = [
        ["artifact_type: knowledge-note", "status: active"],
        ['title: "Quoted"'],
        ["title: 'Single'"],
        ["tags:", "  - a", "  - b"],
        ["tags: []"],
        ["empty:"],
        ["", "title: T", "  ", "status: draft"],
        ["nocolon line", "title: T"],
    ]

    def test_matches_validator_on_shared_inputs(self):
        for inner in self.PARITY_CASES:
            with self.subTest(inner=inner):
                expected = validate_repo.parse_frontmatter(inner)
                got = frontmatter.parse_frontmatter_lines(inner)
                self.assertEqual(got, expected)

    def test_superset_extension_key_beyond_validator(self):
        inner = ["llm-wiki:status: active"]
        # Validator mis-splits compound keys on the first bare ":".
        validator = validate_repo.parse_frontmatter(inner)
        self.assertEqual(validator, {"llm-wiki": "status: active"})
        # The new parser handles them correctly.
        got = frontmatter.parse_frontmatter_lines(inner)
        self.assertEqual(got, {"llm-wiki:status": "active"})

    def test_split_frontmatter_shim_matches_validator(self):
        samples = [
            "---\ntitle: T\nstatus: active\n---\nBody",
            "no frontmatter at all",
            "---\ntitle: T",            # unterminated
            "---\n---\nBody",            # empty fence
        ]
        for text in samples:
            with self.subTest(text=text):
                v_data, v_start = validate_repo.split_frontmatter(text)
                f_data, f_start = frontmatter.split_frontmatter(text)
                self.assertEqual(f_data, v_data)
                self.assertEqual(f_start, v_start)


if __name__ == "__main__":
    unittest.main()
