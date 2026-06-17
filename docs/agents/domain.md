# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

This repo is **multi-context**: a `CONTEXT-MAP.md` at the root points at one `CONTEXT.md` per context. The two expected contexts are the **wiki layer** (the live knowledge base — artifacts, sources, reviews, decisions, workstreams) and the **installer/CLI product** (`src/llm_wiki_wizard/` — scaffolding, templates, the `uvx` wizard). These files are created lazily by `/grill-with-docs`; until then, proceed silently.

## Before exploring, read these

- **`CONTEXT-MAP.md`** at the repo root — it points at one `CONTEXT.md` per context. Read each one relevant to the topic.
- **`CONTEXT.md`** for the specific context you're working in.
- **`docs/adr/`** — read ADRs that touch the area you're about to work in. Also check `src/<context>/docs/adr/` for context-scoped decisions.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The producer skill (`/grill-with-docs`) creates them lazily when terms or decisions actually get resolved.

## File structure

Multi-context repo (presence of `CONTEXT-MAP.md` at the root):

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← system-wide decisions
├── knowledge/ meta/ projects/ …       ← wiki-layer context
│   └── CONTEXT.md                     (or referenced from CONTEXT-MAP.md)
└── src/
    └── llm_wiki_wizard/
        ├── CONTEXT.md                 ← installer/CLI context
        └── docs/adr/                  ← context-specific decisions
```

The exact location of each `CONTEXT.md` is recorded in `CONTEXT-MAP.md` once `/grill-with-docs` seeds it.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in the relevant `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/grill-with-docs`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_
