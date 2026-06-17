# LLM Wiki Starter

Spawn a safe, visible `llm-wiki/` workspace inside any repository. LLM Wiki is a **governed, repo-native, OKF-compatible** workspace for agent-maintained project knowledge: it gives humans and agents a shared, inspectable place for source intake, document decomposition, durable knowledge notes, reviews, decisions, and project coordination without taking over the host repo.

The installer is intentionally conservative: it creates missing files, preserves existing files, and leaves a trace that future agents can validate. Current release: **v0.2.0**.

## Install In An Existing Repo

1. Install or check `uv`:

```bash
uv --version
```

If `uv` is not installed yet, use the official installer from [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/).

2. Preview the install in your target repo:

```bash
uvx --from git+https://github.com/drkolesnikov/llm-wiki-starter llm-wiki init /path/to/repo --dry-run --yes --json
```

3. Create the wiki workspace:

```bash
uvx --from git+https://github.com/drkolesnikov/llm-wiki-starter llm-wiki init /path/to/repo --yes
```

4. Check the installation status:

```bash
uvx --from git+https://github.com/drkolesnikov/llm-wiki-starter llm-wiki status /path/to/repo --json
```

5. Read the generated agent entry point:

```bash
sed -n '1,160p' /path/to/repo/llm-wiki/AGENTS.md
```

6. Validate the generated wiki:

```bash
cd /path/to/repo/llm-wiki
uv run python tools/validate_repo.py
```

## What Gets Created

The installer creates a namespaced wiki at `llm-wiki/` and adds only one host-repo pointer outside that directory. The directory is intentionally visible in macOS Finder and other file browsers.

- `llm-wiki/AGENTS.md`: the first-read file for future agents working in the wiki.
- `llm-wiki/docs/`, `llm-wiki/meta/`, `llm-wiki/raw/`, `llm-wiki/knowledge/`, `llm-wiki/reviews/`, `llm-wiki/projects/`, and `llm-wiki/tools/`: the wiki workspace.
- `llm-wiki/pyproject.toml` and `llm-wiki/uv.lock`: an isolated uv project for wiki tooling, so host dependencies stay untouched.
- `llm-wiki/meta/install.json`: scaffold version, installer version, creation time, layout, and managed-file checksums.
- `llm-wiki/meta/install-report.md`: created files, unchanged files, root pointer action, and any conflicts.
- `AGENTS.md` in the target repo root: a small pointer block telling agents to read `llm-wiki/AGENTS.md`.

## Safety Model

- `init` never overwrites existing target files.
- If a managed file already exists with different content, it is left untouched and recorded in `llm-wiki/meta/install-report.md`.
- Re-running `init` creates only missing managed files and reports conflicts.
- `status` reports missing managed files, changed managed files, root pointer state, scaffold version, and unresolved conflict reports.

## What This Starter Gives You

- A small Markdown knowledge base layout with clear boundaries between `raw/`, `knowledge/`, `reviews/`, `projects/`, `docs/`, and `meta/`.
- A named, versioned **format specification** ([docs/llm-wiki-format.md](docs/llm-wiki-format.md)) — one contract for artifact types, frontmatter fields, allowed values, and conformance.
- A **three-tier validator**: structural validity (blocking, default), portable-profile validity, and an advisory health tier, each invocable independently. New checks are add-a-file via an auto-discovered registry.
- A model-agnostic **wiki health & evaluation suite** (`--tier health`): deterministic duplication, stale-claim, and disambiguation signals, plus optional LLM-backed grounding, contradiction, knowledge-F1, and cross-run-stability signals (off by default).
- A self-contained, offline **governance-aware graph viewer** that colours nodes by review status and source tier and surfaces citations and uncertainty.
- A source registry, source tiers, and ingest rules; **Docling-backed PDF** and **Pandoc-first EPUB** ingest, plus **guarded web ingestion** (explicit seed URLs with host/path/depth/page budgets) and an optional pluggable enrichment agent.
- **Auto-generated, progressive `index.md` navigation** and an append-only maintenance log.
- **Write-time and ingest-time guards** (a pre-commit hook + CI gate) that make destructive edits harder than safe ones.
- Optional **OKF v0.1 interchange**: export the wiki as an OKF bundle (governance metadata carried as extension keys) and import external bundles into a quarantined `needs-review` staging area.
- A `llm-wiki` installer CLI plus local Codex plugin scaffold for creating `llm-wiki/` workspaces inside other repositories.
- Templates for knowledge notes, source summaries, reviews, decisions, query synthesis, workstreams, and agent tasks.

## CLI Commands

The `llm-wiki` CLI (via `uvx` or `uv run`) exposes:

- `init` / `status` — scaffold a `llm-wiki/` workspace into a host repo and report install state.
- `index` (alias `reindex`) — regenerate per-directory `index.md` navigation and append a maintenance-log entry.
- `visualize` — render the self-contained, offline governance-aware HTML graph viewer.
- `enrich` — draft a `needs-review` source summary or note from an already-ingested source (requires a configured model provider; reports disabled otherwise).
- `export` / `import` — render the wiki as an OKF v0.1 bundle, or import an external bundle into staging.

Run `<command> --help` for options; all support `--json` for machine-readable output.

## Working In A Generated Wiki

- Start with `llm-wiki/AGENTS.md`, then read the generated runbooks it points to.
- Register reusable sources in `llm-wiki/meta/source-registry.md` before relying on them in durable notes.
- Keep heavyweight originals out of normal Git unless the generated source policy says otherwise.
- Run `uv run python tools/validate_repo.py` from `llm-wiki/` before handing work off.

## Common Workflows

- Agent handoff: follow the [agent runbook](docs/agent-runbook.md) and [workflow](docs/workflow.md), then report changed files, verification, uncertainty, and next action.
- Source intake: use the [source ingest policy](docs/source-ingest-policy.md), register reusable sources in [source registry](meta/source-registry.md), and keep heavyweight originals out of normal Git.
- Query promotion: use the [query workflow](docs/query-workflow.md) to decide whether a useful answer should stay ephemeral or become a durable artifact.
- Local search: start with [wiki index](meta/index.md), then use the [search workflow](docs/search.md) and `tools/search_wiki.py` when navigation is not enough.
- Wiki health review: run structural validation first, then use [wiki health lint](docs/wiki-health-lint.md) for advisory review signals.

## Developing This Starter

Clone this repository when you want to change the installer, plugin scaffold, vendored template, docs, or local tooling.

Run the repository validator and tests before handing off changes to this starter:

```bash
uv run python tools/validate_repo.py
uv run python -m unittest discover -s tests -v
```

When you change any file under `tools/`, re-sync the vendored installer template so a generated wiki ships the current tooling (the CI drift gate enforces this):

```bash
uv run python tools/sync_vendored.py
```

For advisory wiki health and evaluation signals:

```bash
uv run python tools/validate_repo.py --tier health
```

For a quick search smoke test:

```bash
uv run python tools/search_wiki.py wiki health --limit 5
```

For PDF source ingest, install the optional PDF lane dependencies on demand:

```bash
uv run --group pdf python tools/source-ingest/pdf/ingest_pdf.py --pdf <path> --source-id <id> --source-tier reference --title <title>
```

Run the local installer while developing:

```bash
uv run llm-wiki init /path/to/repo --yes
uv run llm-wiki status /path/to/repo --json
```

The default (structural) tier is blocking and unchanged for CI; the portable-profile and advisory-health tiers are invocable on demand. Evaluation signals are advisory, and the LLM-backed ones are off by default and model-agnostic — factual claims, source disagreement, stale notes, and review quality still benefit from human or agent inspection.

## Repository Shape

```text
AGENTS.md                  Agent entry point and cold-start rules
README.md                  Public landing page
LICENSE                    Project license
.python-version            Default Python version for uv-managed environments
pyproject.toml             uv project metadata and dependency groups
.agents/                   Local Codex plugin marketplace metadata
docs/                      Runbooks, workflows, policies, and templates
meta/                      Index, source registry, and maintenance log
raw/                       Source pointers, external originals, and derivatives
knowledge/                 Durable source-supported notes
reviews/                   Validation and critique artifacts
projects/                  Workstreams, milestones, and project coordination
plugins/                   Local Codex plugin packages
src/                       Python installer package and vendored scaffold template
tools/                     Validation, evaluation, viewer, interchange, search, and source-ingest utilities
tests/                     Test coverage for local tooling
```

## License

This project is licensed under the [MIT License](LICENSE).
