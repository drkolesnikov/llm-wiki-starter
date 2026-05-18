# LLM Wiki Starter

This repository is a blank starter for an agent-maintained Markdown wiki. It gives humans and agents a shared operating surface for source intake, source decomposition, durable notes, decisions, reviews, and project work.

The goal is not to store every source or every conversation. The goal is to keep a clean trail from source material to reusable knowledge, with enough structure that future agents can continue safely.

## Start Here

- [Agent entry point](AGENTS.md)
- [Architecture](docs/architecture.md)
- [Agent runbook](docs/agent-runbook.md)
- [Workflow](docs/workflow.md)
- [Issue workflow](docs/issue-workflow.md)
- [Source ingest policy](docs/source-ingest-policy.md)

## Working Principles

- Keep raw source capture separate from synthesized notes.
- Register sources before relying on them across multiple durable artifacts.
- Use source tiers to make trust and access constraints visible.
- Keep notes small, linkable, source-aware, and reviewable.
- Use workstreams and issues as the visible queue for agent work.
- Make maintenance observable through commits, issues, and `meta/log.md`.

## Repository Shape

```text
AGENTS.md
docs/
  architecture.md
  agent-runbook.md
  workflow.md
  issue-workflow.md
  source-ingest-policy.md
  templates/
meta/
  index.md
  log.md
  source-registry.md
raw/
  sources/
  external/
  derived/
tools/
  validate_repo.py
  source-ingest/pdf/
knowledge/
reviews/
projects/
  workstreams/
  milestones/
```

This starter is intentionally blank. Add real sources, notes, reviews, and workstreams only when they are useful for the current domain.
