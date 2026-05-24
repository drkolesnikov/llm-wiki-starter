import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "llm_wiki_wizard" / "templates" / "wiki"


class EpubIngestDocsTests(unittest.TestCase):
    def test_epub_lane_exists_in_root_and_template(self):
        for base in (ROOT, TEMPLATE):
            with self.subTest(base=base):
                readme = base / "tools" / "source-ingest" / "epub" / "README.md"
                smoke = base / "tools" / "source-ingest" / "epub" / "smoke_test.sh"
                decision = base / "projects" / "epub-ingest-oss-tooling-decision.md"

                self.assertTrue(readme.exists())
                self.assertTrue(smoke.exists())
                self.assertTrue(decision.exists())
                self.assertTrue(os.access(smoke, os.X_OK))

    def test_epub_docs_use_visible_generated_wiki_name(self):
        for base in (ROOT, TEMPLATE):
            with self.subTest(base=base):
                text = (base / "tools" / "source-ingest" / "epub" / "README.md").read_text(encoding="utf-8")
                self.assertIn("llm-wiki/", text)
                self.assertNotIn(".llm-wiki", text)

    def test_epub_tooling_sources_are_registered(self):
        for base in (ROOT, TEMPLATE):
            with self.subTest(base=base):
                registry = (base / "meta" / "source-registry.md").read_text(encoding="utf-8")
                self.assertIn("| pandoc | Pandoc | reference | active | - |", registry)
                self.assertIn("| calibre | Calibre | reference | active | - |", registry)
                self.assertIn("| ebooklib | EbookLib | reference | active | - |", registry)


if __name__ == "__main__":
    unittest.main()
