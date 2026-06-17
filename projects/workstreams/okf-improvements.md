---
artifact_type: workstream
status: active
title: "OKF Improvements Program"
owner: agents
start_date: 2026-06-17
target_date: 2026-06-17
linked_artifacts:
  - ../decisions/adopt-okf-compatibility.md
  - ../../docs/llm-wiki-format.md
---

# OKF Improvements Program

## Outcome

LLM Wiki is a governed, repo-native, portable and interchange-friendly workspace: it borrows OKF's strongest ideas while keeping its stricter governance model. See [Adopt OKF Compatibility](../decisions/adopt-okf-compatibility.md).

## Scope

Derived from GitHub issue #15 (the strategic direction), decomposed into 8 PRDs (#16–#23) and 30 implementation issues (#24–#53), plus an architecture-deepening backlog (#55–#64).

## Active Tasks

- Delivered (#24–#53): a named format spec; a three-tier validator with an auto-discovered checks registry; optional `description` and `resource` frontmatter fields; index and log generation; a governance-aware static graph viewer; guarded web ingestion and enrichment; shared source-registration with write-time and ingest guards plus a CI gate; a model-agnostic wiki health and evaluation suite (seven signals); and optional OKF export and import.
- Delivered (#55–#64, architecture deepening): a single-sourced vendored tool tree (sync script + CI drift gate); one deep Artifact parser (`tools/frontmatter.py`); one `discover_modules` registry helper (fixing non-deterministic command ordering); one `LLMSignal` guard base; and one source-ingest core.
- Open: review and merge the consolidated PR (#54); scope the advisory-health evaluation to the live tree (exclude vendored template copies).

## Source Inputs

- GitHub issue #15 — strategic comparison with GoogleCloudPlatform/knowledge-catalog and OKF v0.1.

## Reviews

- Adversarial Opus review of the issue-slicing plan before implementation; two blockers caught (the missing source-registration writer and the vendored-template drift) and folded into the plan.

## Closeout

- Result: all 8 PRDs and 40 issues (#24–#53 and #55–#64) implemented and integrated; the full test suite is green and the validator passes every tier.
- Follow-up: scope `--tier health` to the live tree; review and merge PR #54.
