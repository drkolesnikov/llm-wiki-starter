---
name: llm-wiki
description: Initialize or inspect a namespaced .llm-wiki workspace in a repository, then route future wiki/source/knowledge work through .llm-wiki/AGENTS.md.
---

# LLM Wiki

Use this skill when a user asks to create, install, spawn, initialize, inspect, or work through an LLM wiki in a repository.

## Initialize

1. Check whether the target repository already has `.llm-wiki/`:

```bash
uv run llm-wiki status <repo> --json
```

2. Initialize with the safe installer:

```bash
uv run llm-wiki init <repo> --yes
```

The installer creates a namespaced `.llm-wiki/` workspace and creates or appends a root `AGENTS.md` pointer block. It never overwrites existing target files; conflicts are recorded in `.llm-wiki/meta/install-report.md`.

## Inspect

Use status before making assumptions about an existing wiki:

```bash
uv run llm-wiki status <repo>
```

If a wiki exists, read `.llm-wiki/AGENTS.md` before creating or changing durable wiki artifacts.

## Work In The Wiki

For future wiki work, treat `.llm-wiki/` as the wiki root. Run wiki validation from that directory:

```bash
cd <repo>/.llm-wiki
uv run python tools/validate_repo.py
```
