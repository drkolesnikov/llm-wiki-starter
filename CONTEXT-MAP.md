# Context Map

This repo has two domain contexts with distinct vocabularies. Skills should read the glossary for the context a task touches.

## Contexts

- [Wiki layer](./CONTEXT.md) — the live, governed knowledge base: artifacts, sources, reviews, decisions, workstreams, and the *interchange surface* that projects them for external tools.
- **Installer / CLI** — `src/llm_wiki_wizard/`: the `uvx` wizard that vendors a clean wiki template and scaffolds a namespaced workspace into a host repo. Glossary pending at `src/llm_wiki_wizard/CONTEXT.md` (created when the first installer-context term is resolved).

## Relationships

- **Installer → Wiki layer**: the installer vendors a *clean* copy of the wiki-layer structure as a template under `src/llm_wiki_wizard/templates/wiki/` and scaffolds it into host repos. The wiki layer in this repo doubles as the product's own live example.
- **Wiki layer → external tools**: the wiki layer exposes an *interchange surface* (first compatibility profile: OKF v0.1) that governance-light consumers can read without understanding the full workflow model.
