# EPUB Source Ingest

The EPUB lane uses established OSS tools instead of a custom parser. The default path is Pandoc for EPUB-to-Markdown or EPUB-to-JSON conversion, with Calibre CLI as the fallback for metadata and difficult ebook normalization.

## Tool Choice

| Tool | Role | Why |
| --- | --- | --- |
| Pandoc | First-choice EPUB to Markdown or JSON conversion. | Mature universal document converter with EPUB reader support and predictable Markdown output. |
| Calibre CLI | Fallback for ebook metadata, inspection, and conversion edge cases. | Mature open-source ebook manager with command-line conversion tools. |
| EbookLib | Reference option only. | Useful Python library for EPUB internals, but using it directly would push the wiki toward maintaining its own parser layer. |

## Installation

On macOS, install the external tools outside the wiki virtual environment:

```bash
brew install pandoc
brew install --cask calibre
```

If Calibre is installed as an app but CLI commands are not on `PATH`, expose them explicitly:

```bash
ln -s "/Applications/calibre.app/Contents/MacOS/ebook-convert" /usr/local/bin/ebook-convert
ln -s "/Applications/calibre.app/Contents/MacOS/ebook-meta" /usr/local/bin/ebook-meta
```

Check availability:

```bash
pandoc --version
ebook-convert --version
ebook-meta --version
```

Run the local smoke test from the wiki root. In a generated host repository, that is `llm-wiki/`:

```bash
bash tools/source-ingest/epub/smoke_test.sh
```

The smoke test creates a tiny legal EPUB under ignored `tmp/`, converts it through the Pandoc-first path, checks Calibre metadata extraction, runs a Calibre normalization pass, and verifies the converted Markdown/JSON outputs. It sets `CALIBRE_CONFIG_DIRECTORY` to `tmp/calibre-config` so the test does not depend on or mutate personal Calibre configuration.

## Ingest Modes

Use the same source policy modes as the rest of the wiki:

- `restricted-pointer-only`: default for newly purchased or uncertain-license ebooks.
- `summary-only`: when only high-level takeaways are needed.
- `selective-page-range`: not naturally page-based for EPUB; use chapter, section, or heading ranges instead.
- `full-local-index`: allowed only when the source is approved for broad local derivation.

## Recommended Output Shape

For an approved EPUB source ID:

```text
raw/derived/<source-id>/
  manifest.yaml
  quality-report.md
  source-summary.md
  source-maps/
    outline.md
  extracted/
    book.md
    book.json
  media/
```

For `summary-only` or restricted books, keep full extracted Markdown/JSON/media under ignored `tmp/` and commit only the smallest useful derivative set:

```text
raw/derived/<source-id>/
  manifest.yaml
  quality-report.md
  source-summary.md
  source-maps/
    outline.md
```

Do not commit the `.epub` original unless a separate source control decision explicitly allows it.

## Pandoc First Pass

Run from the wiki root:

```bash
mkdir -p "raw/derived/<source-id>/extracted" "raw/derived/<source-id>/media" "raw/derived/<source-id>/source-maps"

pandoc "/path/to/book.epub" \
  --from=epub \
  --to=gfm \
  --wrap=none \
  --extract-media="raw/derived/<source-id>/media" \
  --output="raw/derived/<source-id>/extracted/book.md"

pandoc "/path/to/book.epub" \
  --from=epub \
  --to=json \
  --output="raw/derived/<source-id>/extracted/book.json"
```

Use `book.md` for human navigation and `book.json` only when structure-aware downstream tooling needs it.

## Calibre Metadata Check

```bash
CALIBRE_CONFIG_DIRECTORY="$PWD/tmp/calibre-config" \
  ebook-meta "/path/to/book.epub" > "raw/derived/<source-id>/source-maps/metadata.txt"
```

If Pandoc produces poor output, try a Calibre normalization pass into a temporary file outside Git:

```bash
CALIBRE_CONFIG_DIRECTORY="$PWD/tmp/calibre-config" \
  ebook-convert "/path/to/book.epub" "tmp/<source-id>-normalized.epub"

pandoc "tmp/<source-id>-normalized.epub" \
  --from=epub \
  --to=gfm \
  --wrap=none \
  --output="raw/derived/<source-id>/extracted/book.md"
```

## Manual Derivatives

Create these small files by hand after conversion:

- `manifest.yaml`: source ID, title, author, ingest mode, tool versions, original location pointer, derivative paths.
- `quality-report.md`: conversion quality, missing chapters, bad headings, image extraction, footnote/link problems, review status.
- `source-summary.md`: source scope, useful-for, limits, transfer notes, and links to the active workstream.
- `source-maps/outline.md`: chapter or section outline with promotion notes.

## Guardrails

- Use owned, licensed, or otherwise legitimately accessible EPUBs only.
- Do not strip DRM or document workflows for bypassing access controls.
- Do not bulk-copy copyrighted books into durable notes.
- Prefer chapter-level summaries and source maps over full-text knowledge dumps.
- Keep generated smoke-test and scratch outputs under ignored `tmp/` or `scratch/`.
- If conversion quality is poor, mark the source `needs-review` rather than smoothing over missing structure.

## Sources

- Pandoc project: [GitHub](https://github.com/jgm/pandoc), [EPUB docs](https://pandoc.org/epub.html), [install docs](https://pandoc.org/installing.html)
- Calibre project: [GitHub](https://github.com/kovidgoyal/calibre), [conversion docs](https://manual.calibre-ebook.com/en/conversion.html), [`ebook-convert` docs](https://manual.calibre-ebook.com/generated/en/ebook-convert.html)
- EbookLib reference: [GitHub](https://github.com/aerkalov/ebooklib)
