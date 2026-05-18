# Agent Entry Point

This file is the mandatory first read for Codex, Claude Code, and similar repo-editing agents.

This repository is a generic LLM wiki starter. It combines a Markdown knowledge base, source decomposition pipeline, and agent collaboration workflow. The active workstream is the command center when one exists.

## First Reads

Before editing, read:

1. `docs/agent-runbook.md`
2. `docs/workflow.md`
3. `meta/index.md`
4. `meta/source-registry.md`

Then inspect the specific issue, workstream, source, note, review, decision, or task artifact that scopes the work.

## Cold-Start Protocol

1. Restate the current task in repo workflow terms.
2. Identify the active workstream or linked issue, if one exists.
3. Inspect relevant artifacts before creating new ones.
4. Route new artifacts to the correct directory using `docs/agent-runbook.md`.
5. Make only scoped, reviewable edits.
6. Update required links, indexes, source records, and logs.
7. Verify the work and report uncertainty.

## Prime Rules

- Preserve a clear line between source material, parser output, and synthesized knowledge.
- Do not invent source data, decisions, results, or project history.
- Mark incomplete evidence as `needs-review` and unresolved source disagreement as `conflicted`.
- Use committed derivatives before heavyweight originals.
- Cite source ID plus page or chunk ID when available.
- Do not upload or assume access to whole heavyweight originals by default.
- Prefer small, focused notes and reviews over broad dumps.

## Required Updates

When creating or materially changing durable artifacts:

- update `meta/index.md` when navigation or artifact catalog entries change
- update `meta/source-registry.md` before relying on a source across artifacts
- append a concise entry to `meta/log.md`
- link back to the active workstream, issue, review, decision, or source when applicable

## Done Standard

Agent work is done when changed artifacts are in the right place, links are traceable, uncertainty is explicit, verification has run, and `meta/log.md` records the maintenance action.
