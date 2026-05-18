# Agent Runbook

Use this runbook after reading `AGENTS.md`. It tells a cold-start agent how to navigate the repo, route artifacts, and finish work without relying on chat history.

## Cold-Start Checklist

1. Read `AGENTS.md`.
2. Read `docs/workflow.md`.
3. Read `meta/index.md`.
4. Read `meta/source-registry.md`.
5. Read `docs/source-ingest-policy.md` before ingesting, deriving, or summarizing a source.
6. Inspect the issue, workstream, source folder, note, review, or decision that scopes the task.
7. Keep edits scoped to that workflow.

If there is no active workstream or issue, do not invent one unless the task explicitly asks for it.

## Artifact Routing

| Work type | Primary destination | Template or guide | Required control updates |
| --- | --- | --- | --- |
| Workstream planning | `projects/workstreams/` | `docs/templates/workstream.md` | `meta/index.md`, `meta/log.md` |
| Milestones | `projects/milestones/` | local README guidance | `meta/index.md`, `meta/log.md` |
| External originals | external source vault | `raw/external/README.md` | `meta/source-registry.md`, `meta/log.md` |
| Small raw sources | `raw/sources/YYYY-MM-DD_source-slug/` | `raw/sources/README.md` | `meta/source-registry.md`, `meta/log.md` |
| PDF derivatives | `raw/derived/<source-id>/` | `tools/source-ingest/pdf/README.md` | `meta/source-registry.md`, `meta/index.md`, `meta/log.md` |
| Source summaries | source-linked note near relevant workflow | `docs/templates/source-summary.md` | `meta/source-registry.md`, `meta/index.md`, `meta/log.md` |
| Knowledge notes | `knowledge/` | `docs/templates/knowledge-note.md` | `meta/index.md`, source links, `meta/log.md` |
| Reviews | `reviews/` | `docs/templates/review.md` | related artifact links, `meta/index.md`, `meta/log.md` |
| Decisions | `projects/` or `docs/decisions/` if added | `docs/templates/decision.md` | `meta/index.md`, `meta/log.md` |
| Agent tasks | GitHub issue by default | `.github/ISSUE_TEMPLATE/agent-task.md` | active workstream link |
| Navigation and control | `meta/` and `docs/` | existing file style | `meta/log.md` |

## Source And Truth Rules

Use source tiers when sources disagree:

1. `primary`: direct authority for the current domain.
2. `secondary`: strong supporting source.
3. `reference`: useful lookup or background source.
4. `background`: context only.
5. `restricted`: known to the repo but not copied or broadly derived.

Higher-tier sources should be visible in source notes and knowledge notes. If a lower-tier source conflicts with a higher-tier source, preserve the disagreement as `conflicted` rather than smoothing it away.

## Required Updates

Update `meta/index.md` when a durable artifact is created, moved, deprecated, or materially changed.

Update `meta/source-registry.md` when a new source folder is added, a source is used across multiple artifacts, source disagreement matters, or a derivative folder is created under `raw/derived/<source-id>/`.

Append `meta/log.md` when durable artifacts, source ingest outputs, navigation, templates, tools, or agent instructions change.

## Definition Of Done

Agent work is complete when:

- the artifact is in the right directory
- the artifact uses the relevant template or local README convention
- source links are traceable when factual content was added
- uncertainty is marked as `needs-review` or `conflicted`
- required control files are updated
- `python tools/validate_repo.py` has run when workflow, metadata, links, sources, or durable artifacts changed
- verification has run and skipped checks are reported
