"""Sync live tools/ into the installer vendored tree.

Single-sources the vendored tool tree from live ``tools/``.  The canonical
list of files to sync is ``VENDORED_TOOL_FILES`` in
``src/llm_wiki_wizard/installer.py`` — that manifest is the *only* place you
need to touch when adding or removing a tool file from the installer template.

CONTRIBUTOR WORKFLOW
--------------------
1. Edit the live file under ``tools/``.
2. Run this script from the repository root::

       uv run python tools/sync_vendored.py

3. Commit **both** the live edit *and* the updated vendored copy together.

The CI drift gate (``validate.yml``) re-runs this script and fails the build
if the vendored tree does not match the output, so a PR where the two copies
diverge will be rejected automatically.

Usage::

    python tools/sync_vendored.py [--dry-run] [--check]

    --dry-run   Print what would be copied without writing anything.
    --check     Exit non-zero if any file would change (CI mode).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Locate the repository root and import the manifest.
# ---------------------------------------------------------------------------

# This script lives at tools/sync_vendored.py, so the repo root is one level up.
REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_TOOLS = REPO_ROOT / "tools"
VENDORED_TOOLS = REPO_ROOT / "src" / "llm_wiki_wizard" / "templates" / "wiki" / "tools"

# We import the manifest from the installed package (or source tree) so that
# installer.py stays the single authoritative source.
sys.path.insert(0, str(REPO_ROOT / "src"))
from llm_wiki_wizard.installer import VENDORED_TOOL_FILES  # noqa: E402


def _sync(
    *,
    dry_run: bool = False,
    check: bool = False,
) -> int:
    """Copy manifested files from live tools/ into the vendored tree.

    Returns 0 on success, 1 if ``--check`` was requested and drift was found.
    """
    copied: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for rel in VENDORED_TOOL_FILES:
        live = LIVE_TOOLS / rel
        vendored = VENDORED_TOOLS / rel

        if not live.exists():
            errors.append(f"LIVE FILE MISSING (stale manifest entry?): {rel}")
            continue

        live_bytes = live.read_bytes()
        if vendored.exists() and vendored.read_bytes() == live_bytes:
            skipped.append(rel)
            continue

        # File is new or has drifted — copy it.
        if not dry_run and not check:
            vendored.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(live, vendored)

        copied.append(rel)

    # Report.
    for rel in copied:
        tag = "[would copy]" if (dry_run or check) else "[copied]"
        print(f"  {tag}  {rel}")
    for rel in skipped:
        print(f"  [ok]      {rel}")
    for msg in errors:
        print(f"  [ERROR]   {msg}", file=sys.stderr)

    print()
    print(
        f"sync_vendored: {len(copied)} updated, "
        f"{len(skipped)} already in sync, "
        f"{len(errors)} error(s)."
    )

    if errors:
        return 1

    if check and copied:
        print(
            "\nDrift detected — run `uv run python tools/sync_vendored.py` "
            "and commit the result.",
            file=sys.stderr,
        )
        return 1

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync live tools/ into the installer vendored tree.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be copied without writing anything.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if any file would change (CI drift gate mode).",
    )
    args = parser.parse_args()
    sys.exit(_sync(dry_run=args.dry_run, check=args.check))


if __name__ == "__main__":
    main()
