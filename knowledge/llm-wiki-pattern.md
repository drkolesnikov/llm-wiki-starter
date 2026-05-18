---
artifact_type: knowledge-note
status: needs-review
title: "LLM Wiki Pattern"
owner: "agents"
aliases:
  - Karpathy-style LLM Wiki
  - Persistent LLM Wiki
tags:
  - llm-wiki
  - design-memory
sources:
  - karpathy-llm-wiki-pattern
source_count: 1
linked_concepts:
  - "[[LLM Wiki Pattern]]"
  - "[[Query To Artifact]]"
  - "[[Wiki Health]]"
linked_reviews: []
updated: 2026-05-18
---

# LLM Wiki Pattern

## Claim

An LLM wiki is most useful when source intake, durable synthesis, query outputs, reviews, and decisions compound into a persistent Markdown graph that humans and agents can inspect later.

## Source Support

- source_id: `karpathy-llm-wiki-pattern`
- locator: summary-only source registration; no page or chunk locator available
- confidence: medium; source needs review against the authoritative text

## Practical Take

This starter should be treated as a wiki operating system, not just a folder of Markdown files. The valuable behavior is the loop: register sources, derive or summarize only what is needed, write focused notes, review gaps, record decisions, and keep the navigation surface healthy.

## Where The Repo Matches The Pattern

- It separates source identity, parser output, and synthesized knowledge through `meta/source-registry.md`, `raw/`, and `knowledge/`.
- It gives agents a durable control plane through `AGENTS.md`, `docs/agent-runbook.md`, `meta/index.md`, and `meta/log.md`.
- It uses workstreams and issues as visible command centers instead of relying on chat history.

## Where The Repo Extends The Pattern

- It defines source tiers and ingest modes so restricted, heavyweight, or uncertain sources can be handled without bulk copying.
- It includes structural validation for frontmatter, source IDs, derived paths, and local Markdown links.
- It routes reviews and decisions as first-class artifacts instead of treating them as comments around notes.

## Missing Or Newly Added Wiki-Native Behavior

- Obsidian conventions are now documented so future notes can support both validated Markdown links and optional graph-friendly wikilinks.
- Query promotion is now documented so valuable answers can become durable artifacts without archiving every chat.
- Wiki health lint and local search remain later scale-readiness work under M2.

## Repo Implications

- New factual notes should cite registered source IDs and mark incomplete evidence as `needs-review`.
- High-value query answers should use the query workflow before being promoted into knowledge, review, decision, source summary, or workstream artifacts.
- Future graph-health work should look for orphan notes, stale claims, missing source support, unresolved `conflicted` items, and duplicated concepts.

## Open Questions

- `needs-review`: compare the summary-only source record with the authoritative source text before marking this note verified.

## Links

- Workstream: [Wiki Starter Hardening](../projects/workstreams/wiki-starter-hardening.md)
- Source summary: [Karpathy LLM Wiki Pattern Source Summary](karpathy-llm-wiki-pattern-summary.md)
- Source registry: [Source Registry](../meta/source-registry.md)
