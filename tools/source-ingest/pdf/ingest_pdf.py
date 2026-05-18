#!/usr/bin/env python3
"""Create reusable wiki source artifacts from a local PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
SOURCE_TIERS = ("primary", "secondary", "reference", "background", "restricted")


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str
    image_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Decompose a PDF into wiki navigation and search artifacts."
    )
    parser.add_argument("--pdf", required=True, help="Path to the local PDF.")
    parser.add_argument("--source-id", required=True, help="Stable source id, using lowercase words and dashes.")
    parser.add_argument("--source-tier", required=True, choices=SOURCE_TIERS, help="Generic source tier.")
    parser.add_argument("--title", required=True, help="Human-readable source title.")
    parser.add_argument("--output-root", default="raw/derived", help="Folder where derived source folders are written.")
    parser.add_argument("--page-range", default="", help="Optional 1-based ranges such as 1-5,9,12-14.")
    parser.add_argument("--parser-profile", default="pymupdf", choices=("pymupdf",), help="PDF parser profile.")
    parser.add_argument("--max-chars", type=int, default=1800, help="Target maximum characters per chunk.")
    parser.add_argument("--large-source", action="store_true", help="Record that this source is large.")
    parser.add_argument("--extract-figures", action="store_true", help="Extract embedded image files.")
    parser.add_argument("--render-pages", action="store_true", help="Render page preview PNG files.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing derived source folder.")
    parser.add_argument("--vault-id", default="", help="Stable external vault id, if one exists.")
    parser.add_argument("--vault-provider", default="local", help="Vault or storage provider label.")
    parser.add_argument("--original-repo-pointer", default="", help="Repository-relative pointer to a source note or vault README.")
    parser.add_argument("--no-local-path-hint", action="store_true", help="Omit the machine-specific local path hint.")
    return parser.parse_args()


def require_source_id(source_id: str) -> None:
    if not SOURCE_ID_RE.match(source_id):
        raise SystemExit("source-id must use lowercase letters, digits, and dashes.")


def import_fitz():
    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "PyMuPDF is required for PDF ingest. Install tools/source-ingest/pdf/requirements-core.txt."
        ) from exc
    return fitz


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def selected_pages(total_pages: int, page_range: str) -> list[int]:
    if not page_range:
        return list(range(1, total_pages + 1))
    pages: set[int] = set()
    for part in page_range.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start > end:
                start, end = end, start
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))
    invalid = [page for page in pages if page < 1 or page > total_pages]
    if invalid:
        raise SystemExit(f"page-range contains invalid page(s): {invalid}")
    return sorted(pages)


def ensure_output(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise SystemExit(f"Output folder already exists: {path}. Use --overwrite to replace it.")
    if path.exists():
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
    path.mkdir(parents=True, exist_ok=True)
    for name in ("pages", "tables", "figures", "source-maps"):
        (path / name).mkdir(parents=True, exist_ok=True)


def extract_pages(doc, page_numbers: list[int]) -> list[PageText]:
    pages: list[PageText] = []
    for page_number in page_numbers:
        page = doc.load_page(page_number - 1)
        text = page.get_text("text").strip()
        image_count = len(page.get_images(full=True))
        pages.append(PageText(page_number=page_number, text=text, image_count=image_count))
    return pages


def write_page_files(output_dir: Path, pages: list[PageText], source_id: str, title: str) -> None:
    for page in pages:
        stem = f"page-{page.page_number:04d}"
        md_path = output_dir / "pages" / f"{stem}.md"
        json_path = output_dir / "pages" / f"{stem}.json"
        frontmatter = [
            "---",
            "artifact_type: source-map",
            "status: needs-review",
            f"source_id: {source_id}",
            "source_tier: reference",
            f"title: {quote_yaml(title)}",
            f"pdf_page: {page.page_number}",
            f"updated: {date.today().isoformat()}",
            "---",
            "",
            f"# Page {page.page_number}",
            "",
            page.text,
            "",
        ]
        md_path.write_text("\n".join(frontmatter), encoding="utf-8")
        json_path.write_text(
            json.dumps(
                {
                    "source_id": source_id,
                    "page_number": page.page_number,
                    "char_count": len(page.text),
                    "image_count": page.image_count,
                    "text": page.text,
                },
                ensure_ascii=True,
            )
            + "\n",
            encoding="utf-8",
        )


def chunk_pages(pages: list[PageText], max_chars: int) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    current: list[str] = []
    start_page: int | None = None
    end_page: int | None = None

    def flush() -> None:
        nonlocal current, start_page, end_page
        if not current or start_page is None or end_page is None:
            return
        text = "\n\n".join(part for part in current if part).strip()
        if text:
            chunks.append(
                {
                    "chunk_id": f"chunk-{len(chunks) + 1:05d}",
                    "page_start": start_page,
                    "page_end": end_page,
                    "char_count": len(text),
                    "text": text,
                }
            )
        current = []
        start_page = None
        end_page = None

    for page in pages:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", page.text) if part.strip()]
        if not paragraphs:
            paragraphs = [""]
        for paragraph in paragraphs:
            next_size = sum(len(part) for part in current) + len(paragraph) + 2 * len(current)
            if current and next_size > max_chars:
                flush()
            if start_page is None:
                start_page = page.page_number
            end_page = page.page_number
            current.append(paragraph)
    flush()
    return chunks


def write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def toc_rows(doc) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, item in enumerate(doc.get_toc(simple=True), start=1):
        level, title, page_number = item
        rows.append(
            {
                "section_id": f"section-{index:04d}",
                "level": level,
                "title": title,
                "page_number": page_number,
                "anchor": f"pdf-page-{page_number}",
            }
        )
    return rows


def figure_rows(doc, page_numbers: list[int]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for page_number in page_numbers:
        page = doc.load_page(page_number - 1)
        for image_index, image in enumerate(page.get_images(full=True), start=1):
            xref = image[0]
            rows.append(
                {
                    "figure_id": f"figure-p{page_number:04d}-{image_index:03d}",
                    "page_number": page_number,
                    "xref": xref,
                    "width": image[2],
                    "height": image[3],
                    "colorspace": image[5] if len(image) > 5 else "",
                    "extracted": False,
                }
            )
    return rows


def extract_figures(doc, output_dir: Path, rows: list[dict[str, object]]) -> None:
    fitz = import_fitz()
    for row in rows:
        xref = int(row["xref"])
        image = doc.extract_image(xref)
        extension = image.get("ext", "bin")
        filename = f"{row['figure_id']}.{extension}"
        path = output_dir / "figures" / filename
        path.write_bytes(image["image"])
        row["extracted"] = True
        row["path"] = path.relative_to(output_dir).as_posix()
    _ = fitz


def render_pages(doc, output_dir: Path, page_numbers: list[int]) -> None:
    preview_dir = output_dir / "pages" / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    for page_number in page_numbers:
        page = doc.load_page(page_number - 1)
        pixmap = page.get_pixmap(matrix=None)
        pixmap.save(preview_dir / f"page-{page_number:04d}.png")


def write_manifest(
    output_dir: Path,
    args: argparse.Namespace,
    pdf_path: Path,
    page_count: int,
    selected_count: int,
    source_hash: str,
) -> None:
    stat = pdf_path.stat()
    metadata = {
        "source_id": args.source_id,
        "title": args.title,
        "source_tier": args.source_tier,
        "status": "needs-review",
        "parser_profile": args.parser_profile,
        "large_source": bool(args.large_source),
        "created": date.today().isoformat(),
        "pdf": {
            "page_count": page_count,
            "selected_page_count": selected_count,
            "size_bytes": stat.st_size,
            "sha256": source_hash,
        },
        "source_location": {
            "vault_id": args.vault_id,
            "vault_provider": args.vault_provider,
            "original_repo_pointer": args.original_repo_pointer,
            "local_path_hint": "" if args.no_local_path_hint else str(pdf_path),
        },
        "outputs": [
            "manifest.yaml",
            "quality-report.md",
            "source-summary.md",
            "source-maps/outline.md",
            "sections.jsonl",
            "chunks.jsonl",
            "pages/",
            "tables/",
            "figures/",
        ],
    }
    (output_dir / "manifest.yaml").write_text(render_yaml(metadata), encoding="utf-8")


def render_yaml(value: object, indent: int = 0) -> str:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.append(render_yaml(child, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {quote_yaml(child)}")
        return "\n".join(lines) + "\n"
    if isinstance(value, list):
        lines = []
        for child in value:
            if isinstance(child, (dict, list)):
                lines.append(f"{prefix}-")
                lines.append(render_yaml(child, indent + 2).rstrip("\n"))
            else:
                lines.append(f"{prefix}- {quote_yaml(child)}")
        return "\n".join(lines) + "\n"
    return f"{prefix}{quote_yaml(value)}\n"


def quote_yaml(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return '""'
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if re.match(r"^[A-Za-z0-9_./:-]+$", text):
        return text
    return json.dumps(text)


def write_quality_report(output_dir: Path, pages: list[PageText], chunks: list[dict[str, object]], figures: list[dict[str, object]]) -> None:
    empty_pages = [page.page_number for page in pages if not page.text.strip()]
    lines = [
        "# Quality Report",
        "",
        f"- Pages processed: {len(pages)}",
        f"- Empty text pages: {len(empty_pages)}",
        f"- Chunks written: {len(chunks)}",
        f"- Figure metadata rows: {len(figures)}",
        f"- Status: {'needs-review' if empty_pages else 'verified'}",
        "",
        "## Empty Pages",
        "",
    ]
    if empty_pages:
        lines.extend(f"- {page_number}" for page_number in empty_pages)
    else:
        lines.append("- None")
    lines.append("")
    (output_dir / "quality-report.md").write_text("\n".join(lines), encoding="utf-8")


def write_source_summary(output_dir: Path, args: argparse.Namespace, page_count: int, selected_count: int) -> None:
    lines = [
        "---",
        "artifact_type: source-summary",
        "status: needs-review",
        f"source_id: {args.source_id}",
        f"source_tier: {args.source_tier}",
        f"title: {quote_yaml(args.title)}",
        f"updated: {date.today().isoformat()}",
        "---",
        "",
        f"# {args.title}",
        "",
        "## Scope",
        "",
        "This source has been decomposed for navigation and search.",
        "",
        "## Counts",
        "",
        f"- Total PDF pages: {page_count}",
        f"- Processed pages: {selected_count}",
        "",
        "## Review Notes",
        "",
        "- Derived text is `needs-review` until checked in a scoped workstream.",
        "- Source maps are navigation artifacts and do not create durable claims by themselves.",
        "",
    ]
    (output_dir / "source-summary.md").write_text("\n".join(lines), encoding="utf-8")


def write_outline(output_dir: Path, args: argparse.Namespace, sections: list[dict[str, object]], page_count: int) -> None:
    lines = [
        "---",
        "artifact_type: source-map",
        "status: needs-review",
        f"source_id: {args.source_id}",
        f"source_tier: {args.source_tier}",
        f"title: {quote_yaml(args.title)}",
        f"updated: {date.today().isoformat()}",
        "---",
        "",
        f"# {args.title} Outline",
        "",
        "| Section | PDF Page | Anchor |",
        "| --- | ---: | --- |",
    ]
    if sections:
        for section in sections:
            title = str(section["title"]).replace("|", "\\|")
            page_number = section["page_number"]
            anchor = section["anchor"]
            lines.append(f"| {title} | {page_number} | `{anchor}` |")
    else:
        lines.append(f"| Full source | 1-{page_count} | `pdf-page-1` |")
    lines.append("")
    (output_dir / "source-maps" / "outline.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    require_source_id(args.source_id)
    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")
    if not pdf_path.is_file():
        raise SystemExit(f"PDF path is not a file: {pdf_path}")

    fitz = import_fitz()
    output_root = Path(args.output_root).resolve()
    output_dir = output_root / args.source_id
    ensure_output(output_dir, args.overwrite)

    with fitz.open(pdf_path) as doc:
        page_count = doc.page_count
        page_numbers = selected_pages(page_count, args.page_range)
        pages = extract_pages(doc, page_numbers)
        sections = toc_rows(doc)
        figures = figure_rows(doc, page_numbers)
        if args.extract_figures:
            extract_figures(doc, output_dir, figures)
        if args.render_pages:
            render_pages(doc, output_dir, page_numbers)

    chunks = chunk_pages(pages, max(200, args.max_chars))
    source_hash = sha256_file(pdf_path)

    write_manifest(output_dir, args, pdf_path, page_count, len(page_numbers), source_hash)
    write_page_files(output_dir, pages, args.source_id, args.title)
    write_jsonl(output_dir / "sections.jsonl", sections)
    write_jsonl(output_dir / "chunks.jsonl", (dict(chunk, source_id=args.source_id) for chunk in chunks))
    write_jsonl(output_dir / "figures" / "figures.jsonl", figures)
    write_jsonl(output_dir / "tables" / "tables.jsonl", [])
    write_quality_report(output_dir, pages, chunks, figures)
    write_source_summary(output_dir, args, page_count, len(page_numbers))
    write_outline(output_dir, args, sections, page_count)

    print(f"Wrote derived source artifacts to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
