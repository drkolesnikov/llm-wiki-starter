# Issue Workflow

Issues are the visible queue for agent work. They should be small enough to review and specific enough to validate.

## Issue Types

- Agent task: bounded repository change.
- Source ingest: register and decompose a source.
- Knowledge note: create or revise a durable note.
- Review: validate, critique, or repair an artifact.
- Decision: record a choice that future agents need.
- Workstream: coordinate related issues and artifacts.
- Maintenance: clean up structure, tooling, metadata, or links.

## Lifecycle

1. Open the issue with the matching template.
2. Link any active workstream, source, note, review, or decision.
3. State the validation path before implementation begins.
4. Make scoped changes and update control files.
5. Run the validator when metadata, links, sources, or durable artifacts change.
6. Close the issue only after the repository trail is complete.

## Labels

Starter labels can mirror the issue templates:

- `agent-task`
- `source-ingest`
- `knowledge`
- `review`
- `decision`
- `workstream`
- `maintenance`

## Handoff Standard

Every substantial issue update should include changed files, validation run, uncertainty, and the next action.
