#!/usr/bin/env python3
"""Register an EPUB source in the wiki source registry and prepare the output scaffold.

This script does NOT run Pandoc or Calibre itself — that step is intentionally
manual so the operator can review conversion quality before committing derived
files.  What this script *does* do:

1. Validate the source id, tier, and locator via ``registry.register_source``.
2. Create the output directory scaffold (manifest.yaml, empty subdirs).
3. Print the Pandoc/Calibre commands to run next.

Usage
-----
    uv run python tools/source-ingest/epub/ingest_epub.py \\
        --epub /path/to/book.epub \\
        --source-id my-book \\
        --source-tier primary \\
        --title "My Book Title" \\
        --locator "https://example.com/book" \\
        --registry-path meta/source-registry.md \\
        --output-root raw/derived
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml


SOURCE_TIERS = ("primary", "secondary", "reference", "background", "restricted")

# ---------------------------------------------------------------------------
# Shared source-ingest core (source-id validation + registry wiring)
# ---------------------------------------------------------------------------
# Ensure tools/source-ingest/ is importable regardless of working directory.
_SI_DIR = Path(__file__).resolve().parents[1]
if str(_SI_DIR) not in sys.path:
    sys.path.insert(0, str(_SI_DIR))

from core import validate_source_id, wire_registry, derived_output_path  # noqa: E402

_register_source = wire_registry()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register an EPUB source and scaffold the derived output directory."
    )
    parser.add_argument("--epub", required=True, help="Path to the local EPUB file.")
    parser.add_argument(
        "--source-id",
        required=True,
        help="Stable source id using lowercase letters, digits, and dashes.",
    )
    parser.add_argument(
        "--source-tier",
        required=True,
        choices=SOURCE_TIERS,
        help="Source tier.",
    )
    parser.add_argument("--title", required=True, help="Human-readable source title.")
    parser.add_argument(
        "--locator",
        required=True,
        help="Canonical URL or locator for the EPUB source (required for paged/chunked formats).",
    )
    parser.add_argument(
        "--registry-path",
        required=True,
        help="Path to meta/source-registry.md.",
    )
    parser.add_argument(
        "--output-root",
        default="raw/derived",
        help="Folder where derived source folders are written.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing derived source folder.",
    )
    return parser.parse_args(argv)


def yaml_text(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=False)


def ingest_epub(
    args: argparse.Namespace,
    *,
    registry_path: "Path | None" = None,
) -> Path:
    validate_source_id(args.source_id)

    epub_path = Path(args.epub).expanduser().resolve()
    if not epub_path.exists():
        raise SystemExit(f"EPUB not found: {epub_path}")
    if not epub_path.is_file():
        raise SystemExit(f"EPUB path is not a file: {epub_path}")

    # --- registry guard ---
    resolved_registry = registry_path or Path(args.registry_path).expanduser().resolve()
    result = _register_source(
        source_id=args.source_id,
        title=args.title,
        tier=args.source_tier,
        derived_path=derived_output_path(args.output_root, args.source_id),
        locator=args.locator or None,
        format_has_locators=True,
        registry_path=resolved_registry,
    )
    if not result.ok:
        items = ", ".join(result.missing)
        raise SystemExit(
            f"Source registration failed for '{args.source_id}'. "
            f"Missing required field(s): {items}."
        )

    # --- create output scaffold ---
    output_root = Path(args.output_root).resolve()
    output_dir = output_root / args.source_id

    if output_dir.exists() and not args.overwrite:
        raise SystemExit(
            f"Output folder already exists: {output_dir}. Use --overwrite to replace it."
        )

    for sub in ("extracted", "media", "source-maps"):
        (output_dir / sub).mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "source_id": args.source_id,
        "title": args.title,
        "source_tier": args.source_tier,
        "status": "needs-review",
        "format": "epub",
        "locator": args.locator,
        "created": date.today().isoformat(),
        "epub": {
            "path": str(epub_path),
        },
        "outputs": [
            "manifest.yaml",
            "quality-report.md",
            "source-summary.md",
            "source-maps/outline.md",
            "extracted/book.md",
            "extracted/book.json",
            "media/",
        ],
    }
    (output_dir / "manifest.yaml").write_text(yaml_text(manifest), encoding="utf-8")

    return output_dir


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = ingest_epub(args)
    rel = args.output_root + "/" + args.source_id
    print(f"Registered source '{args.source_id}' and scaffolded output at {output_dir}")
    print()
    print("Next step — run Pandoc conversion:")
    print(
        f"  pandoc {args.epub!r} --from=epub --to=gfm --wrap=none"
        f" --extract-media={rel}/media --output={rel}/extracted/book.md"
    )
    print(
        f"  pandoc {args.epub!r} --from=epub --to=json --output={rel}/extracted/book.json"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
