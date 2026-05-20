---
artifact_type: decision
status: active
title: "Package LLM Wiki as a plugin and installer"
owner: agents
linked_artifacts:
  - ../../src/llm_wiki_wizard/cli.py
  - ../../src/llm_wiki_wizard/installer.py
  - ../../plugins/llm-wiki/.codex-plugin/plugin.json
sources: []
updated: 2026-05-20
---

# Package LLM Wiki as a Plugin and Installer

## Context

The starter repo can be cloned directly, but the intended use is broader: agents should be able to spawn the wiki workflow inside any future repository without mixing wiki dependencies into the host project or overwriting host files.

## Decision

Ship an installable `llm-wiki` Python CLI and a local Codex plugin scaffold. The CLI initializes a namespaced `.llm-wiki/` workspace inside a target repo and adds only a small root `AGENTS.md` pointer block outside that namespace.

## Rationale

- A console script gives humans and agents one stable command: `llm-wiki init <repo>`.
- A vendored scaffold keeps generated wikis clean, excluding this repository's sample knowledge, old milestones, demo decisions, and maintenance trail.
- Copier handles template rendering, while a project-owned safe-merge layer controls writes so existing files are never overwritten.
- A nested `.llm-wiki/pyproject.toml` and `.llm-wiki/uv.lock` keep wiki tooling dependencies isolated from the host repository.

## Consequences

- Version 1 supports `init` and `status`; upgrades remain manual.
- Existing target files with different contents are preserved and recorded in `.llm-wiki/meta/install-report.md`.
- Future agent work should inspect `llm-wiki status` first, then read `.llm-wiki/AGENTS.md` before creating durable wiki artifacts.
