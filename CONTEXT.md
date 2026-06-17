# Wiki Layer

The live, governed knowledge base and the vocabulary it maintains over time. This is the primary context: artifacts, sources, and project memory spread across `knowledge/`, `meta/`, `projects/`, `reviews/`, and `docs/`. See [CONTEXT-MAP.md](./CONTEXT-MAP.md) for the other context.

## Language

**Artifact**:
Any governed document the wiki tracks — knowledge-note, source-summary, review, decision, workstream, and the rest of the allow-listed types — carrying required frontmatter and governance metadata.
_Avoid_: concept (reserved for the OKF sense below), page, doc, entry.

**Concept** (OKF sense):
A portable knowledge document as defined by an external interchange format: frontmatter plus a Markdown body, linked into a graph, deliberately governance-light. In this project a concept is a *portable rendering* of an artifact — never a native artifact type.
_Avoid_: using "concept" for internal artifacts (those are artifacts).

**Governance layer**:
The strict internal operating model — required frontmatter, source registration, tiers, review/decision/workstream tracking, uncertainty (`needs-review`) and conflict (`conflicted`) states — that keeps the wiki trustworthy.
_Avoid_: workflow layer, metadata.

**Interchange surface**:
A portable, full-fidelity rendering of the *whole* wiki that external tools consume — the same artifacts as the governance layer, with governance fields carried as optional extension metadata rather than dropped. Everything is rendered; nothing is a hidden subset.
_Avoid_: export, dump, portable layer (use "interchange surface").

**Compatibility profile**:
A named, versioned contract mapping wiki artifacts onto an external interchange format's concept model — which artifacts project to concepts, and how fields map. The first profile targets OKF v0.1.
_Avoid_: adapter, exporter (those name the mechanism; the profile is the contract).

**Open Knowledge Format (OKF)**:
An external, Apache-2.0 Markdown-plus-frontmatter knowledge-bundle format published by Google Cloud (v0.1, 2026-06-12) — a sibling formalization of the Karpathy LLM-wiki pattern, and this project's first compatibility-profile target. Treated as an interchange target, not as the internal model.
_Avoid_: treating OKF as the wiki's native schema.
