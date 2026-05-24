---
artifact_type: decision
status: active
title: "Use OSS Tools For EPUB Ingest"
owner: agents
aliases:
  - EPUB ingest tooling decision
tags:
  - source-ingest
  - epub
  - tooling
sources:
  - pandoc
  - calibre
  - ebooklib
source_count: 3
updated: 2026-05-24
---

# Use OSS Tools For EPUB Ingest

## Decision

The LLM wiki will not build a bespoke EPUB parser for source ingestion. EPUB ingestion should use proven OSS tools:

- Pandoc as the first-choice converter from EPUB to Markdown or JSON.
- Calibre CLI as a fallback for metadata inspection, format normalization, and difficult ebook conversion cases.
- EbookLib as a reference option only, not the default implementation path, because using it directly would make the repo responsible for parser behavior.

## Rationale

The wiki already has a source-ingest policy and a PDF lane. EPUBs are a common format for books and long-form sources, but building a custom parser would create maintenance burden and invite NIH drift. Pandoc and Calibre are mature, cross-platform, open-source tools with active command-line workflows.

## Consequences

- The wiki can ingest approved EPUBs without adding a custom EPUB parsing codebase.
- Tool installation is an environment prerequisite, not a vendored repo dependency.
- Conversion outputs are still derivative artifacts and must follow the source ingest policy.
- Some EPUBs will require manual quality review because ebook structure varies widely.
- DRM removal or access-control bypassing is out of scope.

## Current Environment Check

As of 2026-05-24, Pandoc and Calibre were installed through Homebrew on the test machine:

- `pandoc 3.9.0.2`
- `calibre 9.8.0`
- `ebook-convert (calibre 9.8.0)`
- `ebook-meta (calibre 9.8)`

The local smoke test passed with Pandoc EPUB conversion, Pandoc EPUB-to-Markdown/JSON extraction, Calibre metadata extraction, Calibre EPUB normalization, and a second Pandoc extraction from the normalized EPUB.

For agent and validation runs, use an isolated `CALIBRE_CONFIG_DIRECTORY` under ignored `tmp/` so Calibre does not depend on or mutate personal user preferences.

## Links

- EPUB lane: [EPUB Source Ingest](../tools/source-ingest/epub/README.md)
- Source ingest policy: [Source Ingest Policy](../docs/source-ingest-policy.md)
