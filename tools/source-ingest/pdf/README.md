# PDF Source Ingest

The PDF lane creates navigation and search artifacts from a local PDF while keeping source originals separate from durable wiki notes.

Run from the repository root:

```bash
python tools/source-ingest/pdf/ingest_pdf.py --pdf <path> --source-id <id> --source-tier reference --title <title>
```

Outputs are written to `raw/derived/<source-id>/` by default:

- `manifest.yaml`
- `quality-report.md`
- `sections.jsonl`
- `chunks.jsonl`
- `pages/`
- `tables/`
- `figures/`

Use source maps and summaries for navigation. Promote source material into knowledge notes only through a scoped workstream, review, or decision.
