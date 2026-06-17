"""Tests for pre-commit hook and CI gate adapters (issue #40).

All tests use unittest (not pytest).

Parity guarantee: given equivalent before/after states, ``run_hook`` and
``run_gate`` must produce the SAME blocked verdict as ``evaluate_change``
directly, and must faithfully surface each finding in their message lines.
"""
from __future__ import annotations

import sys
import os
import types
import unittest
from typing import Any

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path so bare ``import tools.*`` works.
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


from tools.preservation import evaluate_change, Finding, Verdict
from tools.hooks.pre_commit_preservation import run_hook
from tools.hooks.ci_preservation_gate import run_gate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(
    *,
    path: str = "notes/test.md",
    title: str = "Test",
    status: str = "active",
    sources: list[str] | None = None,
    body: str = "",
    artifact_type: str = "note",
) -> dict[str, Any]:
    fm: dict[str, Any] = {
        "path": path,
        "title": title,
        "status": status,
        "type": artifact_type,
    }
    if sources is not None:
        fm["sources"] = sources
    return {"frontmatter": fm, "body": body}


# ---------------------------------------------------------------------------
# Parity tests: hook vs engine
# ---------------------------------------------------------------------------

class TestHookAdapterParity(unittest.TestCase):
    """run_hook must produce the same verdict as evaluate_change for every case."""

    def _check_parity(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        *,
        label: str = "",
    ) -> None:
        engine_verdict = evaluate_change(before, after)
        hook_blocked, hook_lines = run_hook(before, after)

        self.assertEqual(
            engine_verdict.blocked,
            hook_blocked,
            f"[hook parity/{label}] blocked mismatch: "
            f"engine={engine_verdict.blocked}, hook={hook_blocked}",
        )

        if engine_verdict.blocked:
            # Every engine finding category must appear in hook output lines.
            combined = "\n".join(hook_lines)
            for finding in engine_verdict.findings:
                self.assertIn(
                    finding.category,
                    combined,
                    f"[hook parity/{label}] finding category '{finding.category}' "
                    f"missing from hook output",
                )

    def test_new_artifact_allow(self) -> None:
        after = _state()
        self._check_parity(None, after, label="new-allow")

    def test_deletion_blocked(self) -> None:
        before = _state()
        self._check_parity(before, None, label="deletion-block")

    def test_clean_edit_allow(self) -> None:
        before = _state(body="## Summary\nsome text\n")
        after = _state(body="## Summary\nsome text updated\n")
        self._check_parity(before, after, label="clean-edit-allow")

    def test_dropped_citation_blocked(self) -> None:
        before = _state(sources=["ref-A"], body="[@ref-A] See this.")
        after = _state(sources=[], body="No citation.")
        self._check_parity(before, after, label="dropped-citation")

    def test_verified_downgrade_blocked(self) -> None:
        before = _state(status="verified")
        after = _state(status="draft")
        self._check_parity(before, after, label="verified-downgrade")

    def test_verified_to_deprecated_blocked(self) -> None:
        before = _state(status="verified")
        after = _state(status="deprecated")
        self._check_parity(before, after, label="verified-to-deprecated")

    def test_no_downgrade_allow(self) -> None:
        before = _state(status="draft")
        after = _state(status="active")
        self._check_parity(before, after, label="no-downgrade-allow")

    def test_multiple_findings_all_surfaced(self) -> None:
        """When multiple destructive changes co-occur, all categories are reported."""
        before = _state(status="verified", sources=["ref-X"])
        after = _state(status="draft", sources=[])
        engine_verdict = evaluate_change(before, after)
        _, hook_lines = run_hook(before, after)
        combined = "\n".join(hook_lines)
        for finding in engine_verdict.findings:
            self.assertIn(finding.category, combined)


# ---------------------------------------------------------------------------
# Parity tests: CI gate vs engine
# ---------------------------------------------------------------------------

class TestCIGateAdapterParity(unittest.TestCase):
    """run_gate must produce the same verdict as evaluate_change for every case."""

    def _check_parity(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        *,
        label: str = "",
    ) -> None:
        engine_verdict = evaluate_change(before, after)
        gate_blocked, gate_lines = run_gate(before, after)

        self.assertEqual(
            engine_verdict.blocked,
            gate_blocked,
            f"[gate parity/{label}] blocked mismatch: "
            f"engine={engine_verdict.blocked}, gate={gate_blocked}",
        )

        if engine_verdict.blocked:
            combined = "\n".join(gate_lines)
            for finding in engine_verdict.findings:
                self.assertIn(
                    finding.category,
                    combined,
                    f"[gate parity/{label}] finding category '{finding.category}' "
                    f"missing from gate output",
                )

    def test_new_artifact_allow(self) -> None:
        after = _state()
        self._check_parity(None, after, label="new-allow")

    def test_deletion_blocked(self) -> None:
        before = _state()
        self._check_parity(before, None, label="deletion-block")

    def test_clean_edit_allow(self) -> None:
        before = _state(body="## Summary\nhello\n")
        after = _state(body="## Summary\nhello world\n")
        self._check_parity(before, after, label="clean-edit-allow")

    def test_dropped_citation_blocked(self) -> None:
        before = _state(sources=["src-1"])
        after = _state(sources=[])
        self._check_parity(before, after, label="dropped-citation")

    def test_verified_downgrade_blocked(self) -> None:
        before = _state(status="active")
        after = _state(status="needs-review")
        self._check_parity(before, after, label="active-to-needs-review")

    def test_multiple_findings_all_surfaced(self) -> None:
        before = _state(status="verified", sources=["s1", "s2"])
        after = _state(status="draft", sources=[])
        engine_verdict = evaluate_change(before, after)
        _, gate_lines = run_gate(before, after)
        combined = "\n".join(gate_lines)
        for finding in engine_verdict.findings:
            self.assertIn(finding.category, combined)


# ---------------------------------------------------------------------------
# Cross-adapter parity: hook and gate produce the SAME result
# ---------------------------------------------------------------------------

class TestCrossAdapterParity(unittest.TestCase):
    """Hook adapter and CI gate must agree on every verdict."""

    def _check_cross(
        self,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        *,
        label: str = "",
    ) -> None:
        hook_blocked, hook_lines = run_hook(before, after)
        gate_blocked, gate_lines = run_gate(before, after)
        self.assertEqual(
            hook_blocked,
            gate_blocked,
            f"[cross-adapter/{label}] hook={hook_blocked}, gate={gate_blocked}",
        )
        # The set of finding categories surfaced must be identical.
        def _categories(lines: list[str]) -> set[str]:
            cats: set[str] = set()
            for line in lines:
                for cat in (
                    "dropped_citation",
                    "deleted_required_section",
                    "broken_source_link",
                    "verified_downgrade",
                    "artifact_deletion",
                ):
                    if cat in line:
                        cats.add(cat)
            return cats

        self.assertEqual(
            _categories(hook_lines),
            _categories(gate_lines),
            f"[cross-adapter/{label}] finding categories differ: "
            f"hook={_categories(hook_lines)}, gate={_categories(gate_lines)}",
        )

    def test_allow_new(self) -> None:
        self._check_cross(None, _state(), label="new")

    def test_block_deletion(self) -> None:
        self._check_cross(_state(), None, label="deletion")

    def test_allow_clean(self) -> None:
        s = _state(body="some body")
        self._check_cross(s, s, label="identical")

    def test_block_dropped_citation(self) -> None:
        before = _state(sources=["ref-Z"], body="[@ref-Z]")
        after = _state(sources=[], body="no ref")
        self._check_cross(before, after, label="dropped-citation")

    def test_block_verified_downgrade(self) -> None:
        before = _state(status="verified")
        after = _state(status="draft")
        self._check_cross(before, after, label="verified-downgrade")


# ---------------------------------------------------------------------------
# Hook exit-code contract
# ---------------------------------------------------------------------------

class TestHookExitBehaviour(unittest.TestCase):
    """run_hook returns (True, non-empty) on block and (False, []) on allow."""

    def test_allow_returns_false_empty_lines(self) -> None:
        before = _state()
        after = _state(body="changed body")
        blocked, lines = run_hook(before, after)
        self.assertFalse(blocked)
        self.assertEqual(lines, [])

    def test_block_returns_true_nonempty_lines(self) -> None:
        before = _state(sources=["must-keep"])
        after = _state(sources=[])
        blocked, lines = run_hook(before, after)
        self.assertTrue(blocked)
        self.assertTrue(len(lines) > 0)

    def test_block_lines_contain_blocked_label(self) -> None:
        before = _state()
        after = None  # deletion
        blocked, lines = run_hook(before, after)
        self.assertTrue(blocked)
        self.assertTrue(any("[BLOCKED]" in line for line in lines))


# ---------------------------------------------------------------------------
# CI gate pass-through contract
# ---------------------------------------------------------------------------

class TestCIGatePassThrough(unittest.TestCase):
    """run_gate returns same structural guarantees as run_hook."""

    def test_allow_returns_false_empty_lines(self) -> None:
        before = _state()
        after = _state(body="different body")
        blocked, lines = run_gate(before, after)
        self.assertFalse(blocked)
        self.assertEqual(lines, [])

    def test_block_returns_true_nonempty_lines(self) -> None:
        before = _state(status="verified")
        after = _state(status="deprecated")
        blocked, lines = run_gate(before, after)
        self.assertTrue(blocked)
        self.assertTrue(len(lines) > 0)

    def test_block_lines_contain_blocked_label(self) -> None:
        before = _state()
        after = None
        blocked, lines = run_gate(before, after)
        self.assertTrue(blocked)
        self.assertTrue(any("[BLOCKED]" in line for line in lines))


# ---------------------------------------------------------------------------
# State-parsing helpers (pre_commit hook)
# ---------------------------------------------------------------------------

class TestHookStateParsing(unittest.TestCase):
    """_parse_artifact and _parse_simple_yaml correctness."""

    def setUp(self) -> None:
        from tools.hooks.pre_commit_preservation import _parse_artifact, _parse_simple_yaml
        self._parse_artifact = _parse_artifact
        self._parse_simple_yaml = _parse_simple_yaml

    def test_none_content_returns_none(self) -> None:
        self.assertIsNone(self._parse_artifact("some.md", None))

    def test_no_frontmatter_returns_body(self) -> None:
        result = self._parse_artifact("a.md", "just body text")
        self.assertIsNotNone(result)
        self.assertIn("just body text", result["body"])

    def test_frontmatter_parsed_correctly(self) -> None:
        content = "---\ntitle: Hello\nstatus: active\n---\n## Body\n"
        result = self._parse_artifact("a.md", content)
        self.assertEqual(result["frontmatter"]["title"], "Hello")
        self.assertEqual(result["frontmatter"]["status"], "active")
        self.assertIn("## Body", result["body"])

    def test_list_field_parsed(self) -> None:
        content = "---\nsources:\n- ref-1\n- ref-2\n---\nbody\n"
        result = self._parse_artifact("a.md", content)
        self.assertEqual(result["frontmatter"]["sources"], ["ref-1", "ref-2"])

    def test_path_injected_into_frontmatter(self) -> None:
        result = self._parse_artifact("notes/foo.md", "no frontmatter")
        self.assertEqual(result["frontmatter"]["path"], "notes/foo.md")


class TestCIGateStateParsing(unittest.TestCase):
    """_parse_artifact in ci_preservation_gate matches hook behaviour."""

    def setUp(self) -> None:
        from tools.hooks.ci_preservation_gate import _parse_artifact
        self._parse_artifact = _parse_artifact

    def test_none_content_returns_none(self) -> None:
        self.assertIsNone(self._parse_artifact("x.md", None))

    def test_frontmatter_parsed(self) -> None:
        content = "---\ntitle: CI\nstatus: verified\n---\nbody text\n"
        result = self._parse_artifact("x.md", content)
        self.assertEqual(result["frontmatter"]["title"], "CI")
        self.assertEqual(result["frontmatter"]["status"], "verified")

    def test_path_in_frontmatter(self) -> None:
        result = self._parse_artifact("docs/spec.md", "plain")
        self.assertEqual(result["frontmatter"]["path"], "docs/spec.md")


if __name__ == "__main__":
    unittest.main()
