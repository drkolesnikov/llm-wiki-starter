#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

for tool in pandoc ebook-convert ebook-meta; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing required tool: $tool" >&2
    exit 1
  fi
done

SOURCE_DIR="tmp/epub-smoke"
OUTPUT_DIR="tmp/derived/epub-smoke"
CALIBRE_CONFIG_DIR="$ROOT/tmp/calibre-config"

rm -rf "$SOURCE_DIR" "$OUTPUT_DIR" "$CALIBRE_CONFIG_DIR"
mkdir -p \
  "$SOURCE_DIR" \
  "$OUTPUT_DIR/extracted" \
  "$OUTPUT_DIR/media" \
  "$OUTPUT_DIR/source-maps" \
  "$CALIBRE_CONFIG_DIR"

cat > "$SOURCE_DIR/book.md" <<'EOF'
% EPUB Smoke Test
% Codex

# Chapter One

This is a small legal test EPUB for the LLM wiki ingestion lane.
EOF

pandoc "$SOURCE_DIR/book.md" \
  --from=markdown \
  --to=epub3 \
  --output="$SOURCE_DIR/book.epub"

pandoc "$SOURCE_DIR/book.epub" \
  --from=epub \
  --to=gfm \
  --wrap=none \
  --extract-media="$OUTPUT_DIR/media" \
  --output="$OUTPUT_DIR/extracted/book.md"

pandoc "$SOURCE_DIR/book.epub" \
  --from=epub \
  --to=json \
  --output="$OUTPUT_DIR/extracted/book.json"

CALIBRE_CONFIG_DIRECTORY="$CALIBRE_CONFIG_DIR" \
  ebook-meta "$SOURCE_DIR/book.epub" > "$OUTPUT_DIR/source-maps/metadata.txt"

CALIBRE_CONFIG_DIRECTORY="$CALIBRE_CONFIG_DIR" \
  ebook-convert "$SOURCE_DIR/book.epub" "$SOURCE_DIR/book-normalized.epub" \
  > "$SOURCE_DIR/ebook-convert.log" 2>&1

pandoc "$SOURCE_DIR/book-normalized.epub" \
  --from=epub \
  --to=gfm \
  --wrap=none \
  --output="$OUTPUT_DIR/extracted/book-normalized.md"

grep -q "Chapter One" "$OUTPUT_DIR/extracted/book.md"
grep -q "Chapter One" "$OUTPUT_DIR/extracted/book-normalized.md"
test -s "$OUTPUT_DIR/extracted/book.json"
test -s "$OUTPUT_DIR/source-maps/metadata.txt"

echo "EPUB smoke test passed."
echo "Outputs:"
find "$OUTPUT_DIR" -type f | sort
