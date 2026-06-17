"""CI preservation gate adapter.

Compares the merge-target (base branch) content of each changed artifact
against the proposed (PR / pushed) content, calls
``tools.preservation.evaluate_change``, and exits non-zero when any verdict is
blocked.

Usage (from the workflow step):
    uv run python tools/hooks/ci_preservation_gate.py \\
        --base-ref origin/main \\
        --head-ref HEAD

The two arguments are git refs that ``git show <ref>:<path>`` can resolve.

Like the pre-commit hook this is a THIN ADAPTER: all logic is in tools.preservation.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _blob(ref: str, path: str) -> str | None:
    """Return text content of ``<ref>:<path>``, or None if absent."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _changed_md_paths(base_ref: str, head_ref: str) -> list[str]:
    """Return Markdown paths that differ between *base_ref* and *head_ref*."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACDMR", base_ref, head_ref],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [p for p in result.stdout.strip().split("\n") if p.endswith(".md")]


# ---------------------------------------------------------------------------
# State parsing (shared logic mirrored from the hook adapter)
# ---------------------------------------------------------------------------


def _parse_simple_yaml(lines: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("- ") and current_list_key is not None:
            result[current_list_key].append(stripped[2:].strip())
            continue
        if ":" in raw:
            key, _, value = raw.partition(":")
            key = key.strip()
            value = value.strip()
            current_list_key = None
            if value == "":
                result[key] = []
                current_list_key = key
            else:
                result[key] = value
        else:
            current_list_key = None
    return result


def _parse_artifact(path: str, content: str | None) -> dict[str, Any] | None:
    if content is None:
        return None
    frontmatter: dict[str, Any] = {}
    body = content
    lines = content.split("\n")
    if lines and lines[0].strip() == "---":
        end = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end = i
                break
        if end is not None:
            frontmatter = _parse_simple_yaml(lines[1:end])
            body = "\n".join(lines[end + 1:])
    frontmatter.setdefault("path", path)
    return {"frontmatter": frontmatter, "body": body, "path": path}


# ---------------------------------------------------------------------------
# Core adapter logic (importable for unit tests)
# ---------------------------------------------------------------------------


def run_gate(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    """Thin pass-through for unit tests: call the engine with explicit states.

    Returns (blocked, message_lines).
    """
    from tools.preservation import evaluate_change

    verdict = evaluate_change(before, after)
    lines: list[str] = []
    if verdict.blocked:
        artifact = (
            (before or after or {}).get("frontmatter", {}).get("path", "<unknown>")
        )
        lines.append(f"[BLOCKED] {artifact}")
        for f in verdict.findings:
            lines.append(f"  • [{f.category}] {f.detail}")
    return verdict.blocked, lines


def evaluate_refs(base_ref: str, head_ref: str) -> tuple[bool, list[str]]:
    """Evaluate all changed Markdown files between two git refs."""
    from tools.preservation import evaluate_change

    paths = _changed_md_paths(base_ref, head_ref)
    any_blocked = False
    lines: list[str] = []
    for path in paths:
        before = _parse_artifact(path, _blob(base_ref, path))
        after = _parse_artifact(path, _blob(head_ref, path))
        verdict = evaluate_change(before, after)
        if verdict.blocked:
            any_blocked = True
            lines.append(f"[BLOCKED] {path}")
            for f in verdict.findings:
                lines.append(f"  • [{f.category}] {f.detail}")
    return any_blocked, lines


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CI preservation gate: compare base vs head and fail on block."
    )
    parser.add_argument("--base-ref", default="origin/main", help="Merge-target ref.")
    parser.add_argument("--head-ref", default="HEAD", help="Proposed ref.")
    args = parser.parse_args()

    blocked, lines = evaluate_refs(args.base_ref, args.head_ref)
    if blocked:
        print(
            "preservation CI gate: BLOCKED — destructive changes detected:",
            file=sys.stderr,
        )
        for line in lines:
            print(line, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
