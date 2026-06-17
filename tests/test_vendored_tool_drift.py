"""Vendored-tool drift test (issue #55).

Byte-compares each file listed in VENDORED_TOOL_FILES (the canonical manifest
of tool files that are vendored into the installer template tree) against its
live twin under tools/.  The test fails when:

  1. A manifested live file is missing from the vendored tree, OR
  2. A manifested file's vendored copy differs from the live source.

To fix a failure: copy the changed live file into the vendored tree (or, if
the file should no longer be vendored, remove it from VENDORED_TOOL_FILES in
src/llm_wiki_wizard/installer.py).
"""

from __future__ import annotations

import unittest
from pathlib import Path

from llm_wiki_wizard.installer import VENDORED_TOOL_FILES


# Repository root is two levels above this file (tests/test_*.py → repo root).
REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_TOOLS = REPO_ROOT / "tools"
VENDORED_TOOLS = REPO_ROOT / "src" / "llm_wiki_wizard" / "templates" / "wiki" / "tools"


class VendoredToolDriftTests(unittest.TestCase):
    """Each manifested file must exist in the vendored tree and be byte-identical."""

    def test_manifest_is_non_empty(self):
        self.assertGreater(
            len(VENDORED_TOOL_FILES),
            0,
            "VENDORED_TOOL_FILES must not be empty",
        )

    def test_no_drift_between_live_and_vendored(self):
        """All manifested files exist in vendored tree and are byte-identical to live."""
        mismatches: list[str] = []
        missing_from_vendored: list[str] = []

        for rel in VENDORED_TOOL_FILES:
            live = LIVE_TOOLS / rel
            vendored = VENDORED_TOOLS / rel

            if not live.exists():
                # Live file missing — this would be a manifest error (stale entry).
                mismatches.append(f"LIVE FILE MISSING (stale manifest entry?): {rel}")
                continue

            if not vendored.exists():
                missing_from_vendored.append(rel)
                continue

            live_bytes = live.read_bytes()
            vendored_bytes = vendored.read_bytes()
            if live_bytes != vendored_bytes:
                mismatches.append(f"CONTENT DIFFERS: {rel}")

        errors: list[str] = []
        if missing_from_vendored:
            errors.append(
                "Manifested tool files missing from vendored tree "
                f"(copy them to src/llm_wiki_wizard/templates/wiki/tools/):\n"
                + "\n".join(f"  {r}" for r in sorted(missing_from_vendored))
            )
        if mismatches:
            errors.append(
                "Vendored copies differ from live source "
                "(re-copy the live file or update the manifest):\n"
                + "\n".join(f"  {m}" for m in sorted(mismatches))
            )

        if errors:
            self.fail("\n\n".join(errors))

    def test_vendored_tree_has_no_extra_python_files_not_in_manifest(self):
        """Every Python file in the vendored tree must appear in VENDORED_TOOL_FILES.

        This catches the reverse drift: a file added to the vendored tree without
        being registered in the manifest.
        """
        manifest_set = set(VENDORED_TOOL_FILES)
        extra: list[str] = []

        for path in VENDORED_TOOLS.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(VENDORED_TOOLS).as_posix()
            if rel not in manifest_set:
                extra.append(rel)

        if extra:
            self.fail(
                "Python files in vendored tree not listed in VENDORED_TOOL_FILES "
                "(add them to the manifest or remove from the tree):\n"
                + "\n".join(f"  {r}" for r in sorted(extra))
            )


if __name__ == "__main__":
    unittest.main()
