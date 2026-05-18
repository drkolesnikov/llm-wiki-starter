---
artifact_type: source-summary
status: needs-review
source_id: "karpathy-llm-wiki-pattern"
source_tier: reference
title: "LLM Wiki pattern / Karpathy-style persistent wiki vision"
updated: 2026-05-18
sources:
  - karpathy-llm-wiki-pattern
aliases:
  - Karpathy LLM Wiki Pattern
tags:
  - source-summary
  - llm-wiki
source_count: 1
linked_concepts:
  - "[[LLM Wiki Pattern]]"
linked_reviews: []
---

# Karpathy LLM Wiki Pattern Source Summary

## Scope

This summary records the design source behind the repo's LLM wiki direction. The source is registered in [source registry](../meta/source-registry.md) as `karpathy-llm-wiki-pattern` with summary-only handling.

## Useful For

- Navigation: explaining why the repo has a source registry, index, workstreams, durable notes, and validation.
- Lookup: finding the practical implications of a persistent agent-maintained wiki.
- Decision support: deciding whether a future feature strengthens source traceability, graph browsing, query promotion, or wiki health.

## Summary

The pattern treats a Markdown wiki as a persistent knowledge workspace that compounds across agent and human sessions. Source material is separated from synthesis. Useful queries can become durable pages. Agents help maintain the graph by adding notes, links, reviews, decisions, and lint results instead of leaving valuable reasoning only in chat.

## Limits

- Access limits: source text is referenced by issue #5 and the registered source ID; no full original is committed.
- Extraction limits: summary-only mode; no page, chunk, or full-text derivatives exist.
- Review needed: compare this summary with the authoritative source text before treating it as verified.

## Derived Artifacts

- Manifest: none.
- Quality report: none.
- Source map: none.
- Related note: [LLM Wiki pattern](llm-wiki-pattern.md).
