# Workflow

This repository is a shared work surface for humans and agents. The workflow should make source use, decisions, open issues, and next actions visible.

## Operating Loop

Use this loop as the default path:

```text
goal
  -> active workstream or issue
  -> source intake
  -> source decomposition
  -> source map or summary
  -> knowledge note or decision
  -> review
  -> follow-up task
  -> maintenance log
```

## Workstreams

A workstream is the command center for a bounded effort. It coordinates sources, notes, reviews, decisions, and agent tasks.

Expected workstream contents:

- goal
- constraints
- source targets
- planned tasks
- review queue
- decisions
- carryover

## Sources

Register sources before using them across durable artifacts. Keep heavyweight originals outside normal Git and commit parser derivatives only when useful.

## Knowledge Notes

Knowledge notes should be focused, source-supported, and easy to revise. Put the practical take first, then source notes and uncertainty.

## Reviews

Reviews capture validation, critique, unresolved questions, and follow-up work. A review should name the artifact it evaluates and the next action.

## Decisions

Decision artifacts record durable choices and the source or reasoning behind them. Use decisions when future agents need the rationale, not just the outcome.
