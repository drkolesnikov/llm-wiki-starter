import tempfile
import unittest
from pathlib import Path

from tools.search_wiki import SearchOptions, discover_markdown_files, search_files


class SearchWikiTests(unittest.TestCase):
    def test_default_search_excludes_external_and_derived_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "knowledge").mkdir()
            (root / "raw" / "external").mkdir(parents=True)
            (root / "raw" / "derived" / "source-a").mkdir(parents=True)
            (root / "knowledge" / "note.md").write_text("Alpha durable note\n", encoding="utf-8")
            (root / "raw" / "external" / "source.md").write_text("Alpha external original\n", encoding="utf-8")
            (root / "raw" / "derived" / "source-a" / "chunk.md").write_text("Alpha derived chunk\n", encoding="utf-8")

            files = list(discover_markdown_files(root, include_derived=False))
            matches = search_files(["alpha"], files, SearchOptions(limit=10))

            self.assertEqual(["knowledge/note.md"], [match.path for match in matches])

    def test_include_derived_adds_raw_derived_without_external_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "knowledge").mkdir()
            (root / "raw" / "external").mkdir(parents=True)
            (root / "raw" / "derived" / "source-a").mkdir(parents=True)
            (root / "knowledge" / "note.md").write_text("Beta durable note\n", encoding="utf-8")
            (root / "raw" / "external" / "source.md").write_text("Beta external original\n", encoding="utf-8")
            (root / "raw" / "derived" / "source-a" / "chunk.md").write_text("Beta derived chunk\n", encoding="utf-8")

            files = list(discover_markdown_files(root, include_derived=True))
            matches = search_files(["beta"], files, SearchOptions(limit=10))

            self.assertEqual(
                ["knowledge/note.md", "raw/derived/source-a/chunk.md"],
                [match.path for match in matches],
            )


if __name__ == "__main__":
    unittest.main()
