# LLM Wiki Format v0.1

This document is the canonical format specification for all artifacts in an LLM wiki repo. It defines artifact types, frontmatter fields, allowed values, the portable-core field set, timestamp semantics, conformance tiers, and the read protocol for agents and tooling.

---

## 1. Artifact Types

Every durable artifact declares an `artifact_type` in its YAML frontmatter. The allowed values are:

| artifact_type | Typical home | Purpose |
| --- | --- | --- |
| `knowledge-note` | `knowledge/` | Synthesised understanding derived from one or more sources |
| `source-summary` | near workflow | Structured summary of a single registered source |
| `source-map` | near workflow | Map of concepts, entities, or structure extracted from a source |
| `source-registry` | `meta/` | Registry table of all ingested or referenced sources |
| `index` | `meta/`, directories | Navigation and catalog artifact |
| `log` | `meta/` | Chronological record of maintenance actions |
| `milestone` | `projects/milestones/` | Project milestone checkpoint |
| `workstream` | `projects/workstreams/` | Active workstream plan and status |
| `review` | `reviews/` | Structured review of an artifact, source, or claim |
| `decision` | `projects/` or `docs/decisions/` | Recorded architectural or workflow decision |
| `agent-task` | GitHub issue | Scoped unit of agent work |
| `source-ingest-policy` | `docs/` | Policy governing how sources are ingested and derived |

---

## 2. Frontmatter Field Catalog

YAML frontmatter is delimited by `---` at the top of the file. The table below covers every recognised field.

| Field | Type | Required / Optional | Meaning |
| --- | --- | --- | --- |
| `artifact_type` | string (enum) | **Required** for durable artifacts | The artifact type; must be one of the allowed values in §1. |
| `title` | string | **Required** for durable artifacts | Human-readable title of the artifact. |
| `description` | string | **Required** for durable artifacts | One- or two-sentence description of the artifact's purpose. |
| `resource` | string or list | Optional | Primary resource(s) this artifact concerns (URL, source ID, or path). |
| `tags` | list of strings | Optional | Free-form topic tags for search and graph navigation. |
| `updated` | string (date) | **Required** for durable artifacts | ISO-8601 date of the last meaningful change (see §5). |
| `status` | string (enum) | **Required** for durable artifacts in `meta/`, `knowledge/`, `reviews/`, `projects/`, `raw/derived/` | Lifecycle status; must be one of the allowed values in §3. |
| `sources` | list of strings | Optional (extension) | Source IDs from `meta/source-registry.md` that this artifact relies on. |
| `source_count` | integer | Optional (extension) | Cached count of registered sources; used in index and registry artifacts. |
| `source_tier` | string (enum) | Optional (extension) | Tier of the primary source (see §3); used in source-facing artifacts. |
| `owner` | string | Optional (extension) | Agent or person responsible for keeping this artifact current. |
| `aliases` | list of strings | Optional (extension) | Alternative titles or slugs for graph link resolution. |
| `linked_concepts` | list of strings | Optional (extension) | Wikilink-style pointers to related concept notes. |
| `linked_reviews` | list of strings | Optional (extension) | Pointers to review artifacts for this artifact. |

---

## 3. Allowed Values

The validator (`tools/validate_repo.py`) enforces these exact sets. Any value not listed is rejected.

### `artifact_type`

```
knowledge-note
source-summary
source-map
source-registry
index
log
milestone
workstream
review
decision
agent-task
source-ingest-policy
```

### `status`

```
draft
active
needs-review
verified
conflicted
deprecated
```

### `source_tier`

```
primary
secondary
reference
background
restricted
```

---

## 4. Core vs. Extension

### Portable Core

The **portable core** is the minimal field set that any conforming tool or agent must understand. It contains exactly:

```
artifact_type
title
description
resource
tags
updated
```

These six fields carry semantic meaning across all artifact types and are sufficient for navigation, search, and basic graph traversal without any domain-specific knowledge.

### Governance Extensions

All other fields are governance extensions — meaningful within this repo's workflow but not required for basic interoperability:

| Extension field | Purpose |
| --- | --- |
| `status` | Lifecycle tracking; required by the structural conformance tier for durable artifacts. |
| `sources` | Source provenance; ties artifacts to the source registry. |
| `source_count` | Cached aggregate for index and registry summaries. |
| `source_tier` | Tier of the primary source; used when source authority matters. |
| `owner` | Accountability and staleness tracking. |
| `aliases` | Graph link resolution for Obsidian and similar tools. |
| `linked_concepts` | Explicit concept-graph edges. |
| `linked_reviews` | Traceability to review artifacts. |

Tools that do not implement governance extensions must ignore unknown fields rather than reject the artifact.

---

## 5. Timestamp Semantics

The `updated` field records the **date of last meaningful change** as an ISO-8601 calendar date (`YYYY-MM-DD`).

Rules:

- Update `updated` when the artifact's content, status, sources, or linked concepts change in a way a reader would notice.
- Do not update `updated` for whitespace-only edits, link-target renames with no semantic change, or automated tooling passes that do not change meaning.
- The date reflects the change date in the author's local timezone; sub-day precision is not required.
- Example valid value: `2025-11-03`

---

## 6. Conformance Tiers

Three tiers of conformance are defined, from most to least strict. The validator runs the structural tier by default; the others are advisory.

### Structural (enforced by `tools/validate_repo.py`)

A file passes the structural tier if:

- It has valid YAML frontmatter delimited by `---`.
- `artifact_type` is present (for durable artifact paths) and is one of the allowed values in §3.
- `status` is present (for durable artifact paths) and is one of the allowed values in §3.
- `source_tier`, when present, is one of the allowed values in §3.
- All `sources` entries resolve to a source ID in `meta/source-registry.md`.
- All standard Markdown links resolve to existing files within the repository.

### Portable-Profile (advisory)

A file meets the portable profile if it passes the structural tier **and**:

- All six portable-core fields (`artifact_type`, `title`, `description`, `resource`, `tags`, `updated`) are present and non-empty.
- `updated` is a valid `YYYY-MM-DD` date string.

This tier is what a conforming external tool needs to consume the artifact without repo-specific logic.

### Advisory-Health (advisory)

A file meets the advisory-health tier if it passes the portable profile **and**:

- `status` is not `needs-review` or `conflicted`.
- The artifact is reachable via at least one standard Markdown link from another artifact (not an orphan).
- All `[[wikilinks]]` in the file resolve to a known title or alias.

Run `uv run python tools/validate_repo.py --health-report` to surface advisory-health signals without failing the build.

---

## 7. Progressive-Disclosure Read Protocol

Agents and tooling should traverse the wiki from coarse to fine, never pulling more than needed:

1. **Start at the directory's `index.md`.** Every directory that contains durable artifacts should have an `index.md` (artifact_type: `index`) that lists and briefly describes the artifacts it contains.
2. **Descend one level at a time.** From the index, follow links to individual artifacts only when the index entry suggests the artifact is relevant to the current task.
3. **Read frontmatter before body.** Frontmatter fields (`title`, `description`, `status`, `tags`) are sufficient to decide whether to read the body. Parse frontmatter first; skip the body if the artifact is out of scope.
4. **Prefer committed derivatives over heavy originals.** When source content is needed, use artifacts in `raw/derived/<source-id>/` before fetching or parsing the original from `raw/external/`.
5. **Stop when scope is satisfied.** Do not continue descending once the artifact, source, or answer needed for the current task is found.

This protocol keeps agent context windows small and avoids loading irrelevant content.
