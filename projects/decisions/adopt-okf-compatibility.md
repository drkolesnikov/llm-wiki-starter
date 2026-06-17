---
artifact_type: decision
status: active
title: "Adopt OKF compatibility as an external interchange goal"
owner: agents
linked_artifacts:
  - ../workstreams/okf-improvements.md
  - ../../docs/llm-wiki-format.md
  - ../../CONTEXT.md
sources: []
updated: 2026-06-17
---

# Adopt OKF Compatibility as an External Interchange Goal

## Context

GitHub issue #15 compared LLM Wiki against Google Cloud's `knowledge-catalog` and its Open Knowledge Format (OKF v0.1, published 2026-06-12). OKF and LLM Wiki are sibling formalizations of the same Karpathy "LLM wiki" pattern: OKF optimizes for portable, data-catalog-flavored interchange; LLM Wiki optimizes for governed, repo-native project memory. The question was whether to adopt OKF, and how.

## Decision

Adopt OKF compatibility as an **external interchange goal** while retaining LLM Wiki's stricter governance model as the internal operating model. Anchor the product identity on **portable interchange**, with OKF v0.1 as the first (and currently only) compatibility profile — not on OKF itself. Mine OKF for good ideas to improve the wiki; treat OKF export/import as one optional capability among several, not the identity.

## Rationale

- Two-layer principle: a simple portable layer that outside tools can consume, plus a richer governance layer (sources, tiers, reviews, decisions, workstreams, uncertainty and conflict states) that keeps the wiki trustworthy.
- Permissive when exporting or consuming OKF; strict when maintaining the wiki internally.
- OKF was five days old with no ecosystem at decision time; welding identity to a single vendor format is fragile, so portability is the anchor and OKF a profile.
- Most borrowed improvements (a named format spec, progressive indexes, a governance-aware viewer, guarded ingestion, write-time guards, health and evaluation signals) are worth doing on their own merits, independent of OKF.

## Consequences

- Implemented via the OKF Improvements program: 8 PRDs (#16–#23) decomposed into 30 issues (#24–#53, merged) plus an architecture-deepening backlog (#55–#64). See the [OKF Improvements workstream](../workstreams/okf-improvements.md).
- The validator now distinguishes structural, portable-profile, and advisory-health tiers; an optional interchange profile exports and imports OKF bundles (export is lossless via extension keys; import quarantines to `needs-review`).
- BigQuery, Dataplex, Vertex, and ADK remain explicitly out of scope (optional adapters only).
