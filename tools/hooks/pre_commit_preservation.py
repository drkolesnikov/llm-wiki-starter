"""Pre-commit hook adapter for the preservation engine.

Gather staged vs. committed artifact states for every changed Markdown file,
call ``tools.preservation.evaluate_change``, and exit non-zero when the verdict
is blocked (itemised findings are printed to stderr).

Installation (one-time, from the repo root):
    ln -sf ../../tools/hooks/pre_commit_preservation.py .git/hooks/pre-commit
Or run directly with the test helper ``run_hook(before, after)`` for unit tests.

The hook is a THIN ADAPTER: all detection logic lives in tools.preservation.
"""
from __future__ import annotations

import subprocess
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git(*args: str) -> str:
    """Run a git command and return stdout (decoded, trailing whitespace stripped)."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
    )
    return result.stdout.rstrip()


def _blob_content(ref: str) -> str | None:
    """Return the text content of *ref* (e.g. ``HEAD:foo.md`` or ``:foo.md``).

    Returns ``None`` if the ref does not exist (new / deleted file).
    """
    result = subprocess.run(
        ["git", "show", ref],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


# ---------------------------------------------------------------------------
# State parsing
# ---------------------------------------------------------------------------


def _parse_artifact(path: str, content: str | None) -> dict[str, Any] | None:
    """Convert raw Markdown *content* into the state dict expected by evaluate_change.

    Returns ``None`` when *content* is ``None`` (file absent in that tree).

    The state format is::

        {
            "frontmatter": {<yaml key-value pairs>},
            "body": "<markdown body text>",
            "path": "<relative file path>",
        }

    We do a minimal YAML parse without requiring PyYAML: split on ``---`` fences
    and parse ``key: value`` lines.  Complex YAML (lists, nested maps) is handled
    for the ``sources`` list key only (``- item`` lines after the list key).
    """
    if content is None:
        return None

    frontmatter: dict[str, Any] = {}
    body = content

    lines = content.split("\n")
    if lines and lines[0].strip() == "---":
        # find closing fence
        end = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end = i
                break
        if end is not None:
            fm_lines = lines[1:end]
            body = "\n".join(lines[end + 1:])
            frontmatter = _parse_simple_yaml(fm_lines)

    frontmatter.setdefault("path", path)
    return {"frontmatter": frontmatter, "body": body, "path": path}


def _parse_simple_yaml(lines: list[str]) -> dict[str, Any]:
    """Parse a small subset of YAML: scalar key-value and simple list values."""
    result: dict[str, Any] = {}
    current_list_key: str | None = None

    for raw in lines:
        # List item continuation
        stripped = raw.strip()
        if stripped.startswith("- ") and current_list_key is not None:
            result[current_list_key].append(stripped[2:].strip())
            continue

        # Key: value
        if ":" in raw:
            key, _, value = raw.partition(":")
            key = key.strip()
            value = value.strip()
            current_list_key = None
            if value == "":
                # This might be the start of a block list
                result[key] = []
                current_list_key = key
            else:
                result[key] = value
        else:
            current_list_key = None

    return result


# ---------------------------------------------------------------------------
# Core adapter logic (importable for unit tests)
# ---------------------------------------------------------------------------


def gather_changed_paths() -> list[str]:
    """Return the list of Markdown paths that are staged for commit."""
    diff_output = _git("diff", "--cached", "--name-only", "--diff-filter=ACDMR")
    if not diff_output:
        return []
    return [p for p in diff_output.split("\n") if p.endswith(".md")]


def get_before_state(path: str) -> dict[str, Any] | None:
    """Return the committed (HEAD) state for *path*, or None if new."""
    content = _blob_content(f"HEAD:{path}")
    return _parse_artifact(path, content)


def get_after_state(path: str) -> dict[str, Any] | None:
    """Return the staged (index) state for *path*, or None if deleted."""
    content = _blob_content(f":{path}")
    return _parse_artifact(path, content)


def evaluate_paths(paths: list[str]) -> tuple[bool, list[str]]:
    """Evaluate all *paths* via the engine.  Return (any_blocked, message_lines).

    This function is importable so unit tests can drive the adapter logic without
    spawning a subprocess or touching real git state.
    """
    from tools.preservation import evaluate_change  # thin import

    any_blocked = False
    lines: list[str] = []

    for path in paths:
        before = get_before_state(path)
        after = get_after_state(path)
        verdict = evaluate_change(before, after)
        if verdict.blocked:
            any_blocked = True
            lines.append(f"[BLOCKED] {path}")
            for f in verdict.findings:
                lines.append(f"  • [{f.category}] {f.detail}")

    return any_blocked, lines


def run_hook(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    """Thin pass-through for unit tests: call the engine with explicit states.

    Returns (blocked, message_lines) identical to what the hook would print/exit.
    This lets tests verify hook behaviour without real git trees.
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


# ---------------------------------------------------------------------------
# Entry point (called by git)
# ---------------------------------------------------------------------------


def main() -> int:
    """Run the pre-commit preservation check.  Returns exit code."""
    paths = gather_changed_paths()
    if not paths:
        return 0

    blocked, lines = evaluate_paths(paths)
    if blocked:
        print(
            "preservation pre-commit hook: BLOCKED — destructive changes detected:",
            file=sys.stderr,
        )
        for line in lines:
            print(line, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
