# Query Workflow

This workflow decides when a useful question-and-answer session should become durable wiki material.

## Decision Rule

Keep an answer ephemeral when it only helps the current conversation, has no reusable source trail, or would duplicate an existing artifact.

Promote an answer when it creates reusable structure. Use the smallest durable route:

| Query Output | Durable Route | Use When |
| --- | --- | --- |
| Narrow sourced claim | Knowledge note | The answer preserves a reusable fact, comparison, or concept. |
| Validation or critique | Review note | The answer evaluates an artifact, finds gaps, or creates follow-up work. |
| Durable choice | Decision artifact | Future agents need the rationale, not just the outcome. |
| Source interpretation | Source summary | The answer summarizes a registered source or source slice. |
| Project progress | Workstream update | The answer changes active tasks, sequencing, carryover, or closeout state. |
| Current-only help | No artifact | The answer has no future navigation or source value. |

## Promotion Requirements

Before promoting a query answer, agents must:

- inspect `meta/index.md` and the relevant workstream or issue to avoid duplicates,
- cite registered source IDs when factual content is promoted,
- register any new source in `meta/source-registry.md` before relying on it across artifacts,
- mark incomplete evidence as `needs-review`,
- mark unresolved source disagreement as `conflicted`,
- write the artifact so it stands on its own without chat history.

## Required Control Updates

Update `meta/index.md` when the promoted artifact should be easy for future agents to find.

Append `meta/log.md` when the promoted artifact is durable, changes navigation, changes source use, or materially updates workflow state.

Use [query synthesis template](templates/query-synthesis.md) for a reusable answer that is not clearly better expressed as an existing knowledge note, review, decision, source summary, or workstream update.

## Anti-Patterns

- Do not archive whole chat transcripts as wiki pages.
- Do not file every answer into the wiki.
- Do not promote unsupported claims just because they sound useful.
- Do not rely on "as discussed in chat" as the only evidence.
