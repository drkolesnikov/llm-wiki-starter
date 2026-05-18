---
artifact_type: milestone
status: verified
title: "M1 Wiki Foundation"
owner: "agents"
start_date: 2026-05-18
target_date: 2026-05-22
linked_artifacts:
  - ../workstreams/wiki-starter-hardening.md
---

# M1 Wiki Foundation

## Outcome

The wiki starter has baseline automation, Obsidian-facing conventions, durable query routing, and a concise design-memory source note.

## Issues

| Wave | Issue | Owner Lane | Status | Acceptance Focus |
| --- | --- | --- | --- | --- |
| Wave A | [#6 Wire validate_repo.py into GitHub Actions](https://github.com/abrapacabra/llm-wiki-starter/issues/6) | Agent A | complete | Workflow runs `python tools/validate_repo.py` on pull requests and pushes to `main`. |
| Wave A | [#1 Add Obsidian-native wiki conventions](https://github.com/abrapacabra/llm-wiki-starter/issues/1) | Agent B | complete | Conventions doc exists, templates include metadata, and validator still passes. |
| Wave B | [#2 Define query-to-durable-artifact workflow](https://github.com/abrapacabra/llm-wiki-starter/issues/2) | Agent C | complete | Workflow distinguishes ephemeral answers from durable notes, reviews, decisions, source summaries, and workstream updates. |
| Wave B | [#5 Register Karpathy LLM Wiki pattern as a design source](https://github.com/abrapacabra/llm-wiki-starter/issues/5) | Agent D | complete | `karpathy-llm-wiki-pattern` is registered as `reference`, summary-only use is explicit, and a durable note cites the source ID. |

## Coordination

- Merge #6 before other issue PRs when practical.
- Start #2 and #5 only after #1 lands.
- Expect `meta/index.md` and `meta/log.md` overlap in Wave B; coordinator resolves those conflicts.

## Validation

- Run `python3 tools/validate_repo.py` before each PR handoff.
- Confirm linked GitHub issues remain assigned to the `M1 Wiki Foundation` milestone.

## Result

- CI validation workflow added.
- Obsidian conventions and wiki metadata template updates added.
- Query-to-artifact workflow and query synthesis template added.
- Karpathy LLM Wiki pattern registered as a summary-only reference source with a source summary and design-memory note.
- Remaining review point: the Karpathy pattern artifacts are `needs-review` until checked against the authoritative source text.
