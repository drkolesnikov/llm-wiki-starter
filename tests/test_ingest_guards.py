"""Tests for ingest-time registration guards (issue #41).

Verifies:
- PDF/EPUB ingest lacking a locator is refused with an itemized reason when a
  registry path is provided.
- A fully valid PDF/EPUB ingest registers via the shared registry and succeeds.
- Existing PDF/EPUB ingest tests still pass (covered by their own modules; a
  smoke-call here confirms the guard does NOT fire when no registry path is
  supplied).
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF_INGEST_PATH = ROOT / "tools" / "source-ingest" / "pdf" / "ingest_pdf.py"
EPUB_INGEST_PATH = ROOT / "tools" / "source-ingest" / "epub" / "ingest_epub.py"


# ---------------------------------------------------------------------------
# Module loaders
# ---------------------------------------------------------------------------

def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"Could not load {path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


ingest_pdf = _load_module(PDF_INGEST_PATH, "_test_ingest_pdf_guards")
ingest_epub = _load_module(EPUB_INGEST_PATH, "_test_ingest_epub_guards")


# ---------------------------------------------------------------------------
# Minimal Docling fakes (mirrors test_pdf_ingest.py)
# ---------------------------------------------------------------------------

class _FakeImage:
    def save(self, path, format=None):
        Path(path).write_bytes(b"png")


class _FakePageImage:
    pil_image = _FakeImage()


class _FakePage:
    def __init__(self, page_no):
        self.page_no = page_no
        self.image = _FakePageImage()


class _FakeProv:
    def __init__(self, page_no):
        self.page_no = page_no


class _SectionHeaderItem:
    text = "Intro"
    level = 1
    prov = [_FakeProv(1)]


class _FakePicture:
    label = "picture"
    caption = "Diagram"
    prov = [_FakeProv(1)]

    def get_image(self, doc):
        return _FakeImage()


class _FakeFrame:
    def to_csv(self, path, index=False):
        Path(path).write_text("name,value\nalpha,1\n", encoding="utf-8")


class _FakeTable:
    prov = [_FakeProv(1)]

    def export_to_dataframe(self, doc):
        return _FakeFrame()

    def export_to_html(self, doc):
        return "<table><tr><td>alpha</td></tr></table>"

    def get_image(self, doc):
        return _FakeImage()


class _FakeDocument:
    def __init__(self, page_numbers=(1, 2)):
        self.page_numbers = tuple(sorted(page_numbers))
        self.pages = {pn: _FakePage(pn) for pn in self.page_numbers}
        self.tables = [_FakeTable()] if 1 in self.page_numbers else []

    def filter(self, page_nrs=None):
        return _FakeDocument(page_nrs or self.page_numbers)

    def export_to_markdown(self, page_no=None, **kwargs):
        if page_no is not None:
            return f"# Page {page_no}\n\nContent from page {page_no}"
        return "\n\n".join(
            f"# Page {pn}\n\nContent from page {pn}" for pn in self.page_numbers
        )

    def export_to_dict(self):
        return {
            "pages": [
                {"page_no": pn, "items": [{"label": "picture"}]}
                for pn in self.page_numbers
            ]
        }

    def iterate_items(self, *args, **kwargs):
        yield _SectionHeaderItem(), 0
        if kwargs.get("traverse_pictures"):
            yield _FakePicture(), 0


class _FakeResult:
    status = "SUCCESS"
    errors = []
    document = _FakeDocument()


class _FakeInputFormat:
    PDF = "pdf"


class _FakePdfPipelineOptions:
    pass


class _FakePdfFormatOption:
    def __init__(self, pipeline_options):
        self.pipeline_options = pipeline_options


class _FakeConverter:
    def __init__(self, format_options):
        pass

    def convert(self, source, raises_on_error=True, page_range=None):
        return _FakeResult()


class _FakeChunk:
    text = "Chunk text"
    meta = {"doc_items": [{"prov": [{"page_no": 1}]}]}


class _FakeHybridChunker:
    def chunk(self, dl_doc):
        return [_FakeChunk()]

    def contextualize(self, chunk):
        return chunk.text


def _fake_runtime():
    return ingest_pdf.DoclingRuntime(
        DocumentConverter=_FakeConverter,
        PdfFormatOption=_FakePdfFormatOption,
        PdfPipelineOptions=_FakePdfPipelineOptions,
        InputFormat=_FakeInputFormat,
        HybridChunker=_FakeHybridChunker,
        PictureItem=_FakePicture,
        TableItem=_FakeTable,
    )


# ---------------------------------------------------------------------------
# Helper: create a minimal registry file
# ---------------------------------------------------------------------------

def _make_registry(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Source Registry\n\n"
        "| Source ID | Title | Tier | Status | Derived Path | Notes |\n"
        "| --- | --- | --- | --- | --- | --- |\n",
        encoding="utf-8",
    )


# ===========================================================================
# PDF guard tests
# ===========================================================================

class PdfIngestGuardTests(unittest.TestCase):

    def _base_pdf_args(self, tmp: str, extra: list[str] | None = None) -> list[str]:
        root = Path(tmp)
        pdf = root / "input.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        output_root = root / "derived"
        argv = [
            "--pdf", str(pdf),
            "--source-id", "my-source",
            "--source-tier", "primary",
            "--title", "My Source",
            "--output-root", str(output_root),
            "--overwrite",
        ]
        if extra:
            argv.extend(extra)
        return argv

    def test_pdf_ingest_without_locator_is_refused_when_registry_provided(self):
        """PDF ingest with a registry path but no --locator must be refused."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "meta" / "source-registry.md"
            _make_registry(registry)
            argv = self._base_pdf_args(tmp, [
                "--registry-path", str(registry),
                # no --locator
            ])
            args = ingest_pdf.parse_args(argv)
            with self.assertRaises(SystemExit) as ctx:
                ingest_pdf.ingest_pdf(
                    args,
                    runtime=_fake_runtime(),
                    page_count_reader=lambda path: 2,
                )
            msg = str(ctx.exception)
            # Must surface itemized reason
            self.assertIn("locator", msg)

    def test_pdf_ingest_missing_locator_error_is_itemized(self):
        """The SystemExit message names 'locator' specifically."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "meta" / "source-registry.md"
            _make_registry(registry)
            argv = self._base_pdf_args(tmp, ["--registry-path", str(registry)])
            args = ingest_pdf.parse_args(argv)
            with self.assertRaises(SystemExit) as ctx:
                ingest_pdf.ingest_pdf(
                    args,
                    runtime=_fake_runtime(),
                    page_count_reader=lambda path: 2,
                )
            self.assertIn("locator", str(ctx.exception))
            self.assertIn("Missing required field", str(ctx.exception))

    def test_pdf_valid_ingest_registers_source_and_succeeds(self):
        """A fully-valid PDF ingest (with locator + registry) completes and writes the registry row."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "meta" / "source-registry.md"
            _make_registry(registry)
            argv = self._base_pdf_args(tmp, [
                "--registry-path", str(registry),
                "--locator", "https://example.com/paper.pdf",
            ])
            args = ingest_pdf.parse_args(argv)
            output_dir = ingest_pdf.ingest_pdf(
                args,
                runtime=_fake_runtime(),
                page_count_reader=lambda path: 2,
            )
            self.assertTrue(output_dir.exists())
            # Registry must contain the source row.
            registry_text = registry.read_text(encoding="utf-8")
            self.assertIn("my-source", registry_text)
            self.assertIn("My Source", registry_text)
            self.assertIn("https://example.com/paper.pdf", registry_text)

    def test_pdf_ingest_without_registry_path_skips_guard(self):
        """When no registry path is provided or auto-detected, ingest proceeds without guard."""
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._base_pdf_args(tmp)
            # No --registry-path, no meta/source-registry.md on disk -> guard skipped.
            args = ingest_pdf.parse_args(argv)
            output_dir = ingest_pdf.ingest_pdf(
                args,
                runtime=_fake_runtime(),
                page_count_reader=lambda path: 2,
            )
            self.assertTrue(output_dir.exists())

    def test_pdf_ingest_registry_result_contains_correct_tier(self):
        """The registered row must carry the correct tier."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "meta" / "source-registry.md"
            _make_registry(registry)
            argv = self._base_pdf_args(tmp, [
                "--registry-path", str(registry),
                "--locator", "https://example.com/paper.pdf",
                "--source-tier", "reference",
            ])
            args = ingest_pdf.parse_args(argv)
            ingest_pdf.ingest_pdf(
                args,
                runtime=_fake_runtime(),
                page_count_reader=lambda path: 2,
            )
            registry_text = registry.read_text(encoding="utf-8")
            self.assertIn("reference", registry_text)


# ===========================================================================
# EPUB guard tests
# ===========================================================================

class EpubIngestGuardTests(unittest.TestCase):

    def _minimal_epub(self, root: Path) -> Path:
        """Create a tiny file that stands in for an EPUB during tests."""
        epub = root / "book.epub"
        epub.write_bytes(b"PK\x03\x04")  # ZIP magic bytes, good enough for path checks
        return epub

    def test_epub_ingest_without_locator_is_refused(self):
        """EPUB ingest with an empty locator must be refused with itemized reason."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            epub = self._minimal_epub(root)
            registry = root / "meta" / "source-registry.md"
            _make_registry(registry)
            output_root = root / "derived"

            args = ingest_epub.parse_args([
                "--epub", str(epub),
                "--source-id", "my-epub",
                "--source-tier", "primary",
                "--title", "My EPUB",
                "--locator", "",         # explicitly empty → triggers guard
                "--registry-path", str(registry),
                "--output-root", str(output_root),
            ])
            # Override locator to empty so the guard fires.
            args.locator = ""
            with self.assertRaises(SystemExit) as ctx:
                ingest_epub.ingest_epub(args)
            self.assertIn("locator", str(ctx.exception))

    def test_epub_ingest_missing_locator_error_is_itemized(self):
        """The SystemExit message from the EPUB guard names 'locator' and 'Missing'."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            epub = self._minimal_epub(root)
            registry = root / "meta" / "source-registry.md"
            _make_registry(registry)
            output_root = root / "derived"
            args = ingest_epub.parse_args([
                "--epub", str(epub),
                "--source-id", "my-epub",
                "--source-tier", "secondary",
                "--title", "My EPUB",
                "--locator", "placeholder",
                "--registry-path", str(registry),
                "--output-root", str(output_root),
            ])
            args.locator = ""  # force missing
            with self.assertRaises(SystemExit) as ctx:
                ingest_epub.ingest_epub(args)
            msg = str(ctx.exception)
            self.assertIn("locator", msg)
            self.assertIn("Missing required field", msg)

    def test_epub_valid_ingest_registers_source_and_succeeds(self):
        """A fully-valid EPUB ingest creates the scaffold and writes the registry row."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            epub = self._minimal_epub(root)
            registry = root / "meta" / "source-registry.md"
            _make_registry(registry)
            output_root = root / "derived"

            args = ingest_epub.parse_args([
                "--epub", str(epub),
                "--source-id", "my-epub",
                "--source-tier", "primary",
                "--title", "My EPUB",
                "--locator", "https://example.com/book.epub",
                "--registry-path", str(registry),
                "--output-root", str(output_root),
            ])
            output_dir = ingest_epub.ingest_epub(args)
            self.assertTrue(output_dir.exists())
            self.assertTrue((output_dir / "manifest.yaml").exists())
            self.assertTrue((output_dir / "extracted").exists())
            self.assertTrue((output_dir / "source-maps").exists())
            # Registry must contain the source row.
            registry_text = registry.read_text(encoding="utf-8")
            self.assertIn("my-epub", registry_text)
            self.assertIn("My EPUB", registry_text)
            self.assertIn("https://example.com/book.epub", registry_text)

    def test_epub_ingest_bad_source_id_is_rejected(self):
        """Malformed source ids (uppercase, underscores) are rejected before registration."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            epub = self._minimal_epub(root)
            registry = root / "meta" / "source-registry.md"
            _make_registry(registry)
            output_root = root / "derived"
            args = ingest_epub.parse_args([
                "--epub", str(epub),
                "--source-id", "Bad_ID",
                "--source-tier", "primary",
                "--title", "Bad",
                "--locator", "https://example.com/book.epub",
                "--registry-path", str(registry),
                "--output-root", str(output_root),
            ])
            with self.assertRaises(SystemExit):
                ingest_epub.ingest_epub(args)

    def test_epub_overwrite_required_for_existing_output(self):
        """A second ingest without --overwrite must be refused."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            epub = self._minimal_epub(root)
            registry = root / "meta" / "source-registry.md"
            _make_registry(registry)
            output_root = root / "derived"

            # First run succeeds.
            args = ingest_epub.parse_args([
                "--epub", str(epub),
                "--source-id", "my-epub",
                "--source-tier", "primary",
                "--title", "My EPUB",
                "--locator", "https://example.com/book.epub",
                "--registry-path", str(registry),
                "--output-root", str(output_root),
            ])
            ingest_epub.ingest_epub(args)

            # Second run without --overwrite must fail.
            args2 = ingest_epub.parse_args([
                "--epub", str(epub),
                "--source-id", "my-epub",
                "--source-tier", "primary",
                "--title", "My EPUB",
                "--locator", "https://example.com/book.epub",
                "--registry-path", str(registry),
                "--output-root", str(output_root),
            ])
            with self.assertRaises(SystemExit):
                ingest_epub.ingest_epub(args2)


if __name__ == "__main__":
    unittest.main()
