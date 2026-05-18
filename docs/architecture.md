# Architecture

## Intent

This repository is a reusable operating system for an agent-maintained Markdown wiki. It keeps source intake, source decomposition, durable knowledge, decisions, reviews, and work planning in one inspectable project.

It should help answer:

- What are we trying to understand or build right now?
- Which source supports this note or decision?
- What has been reviewed, corrected, or deferred?
- Which unresolved issue should be handled next?
- What should a human or agent do safely from here?

## System Model

The project has six cooperating layers.

### 1. Source Intake Layer

Source intake stores source identities, local pointers, and parser-derived artifacts.

Expected artifacts:

- source records in `meta/source-registry.md`
- small source folders under `raw/sources/`
- heavyweight original pointers under ignored `raw/external/`
- derived PDF artifacts under `raw/derived/<source-id>/`
- page anchors, chunks, tables, figure metadata, manifests, and quality reports

### 2. Knowledge Layer

The knowledge layer contains durable source-supported notes in Markdown.

Expected artifacts:

- focused knowledge notes
- claim or concept summaries
- source-linked maps
- decision-relevant comparisons

The goal is durable structure, not a pile of unreviewed excerpts.

### 3. Review Layer

The review layer captures validation work, critique, open questions, and repair items.

Expected artifacts:

- review notes
- issue analysis
- unresolved questions
- follow-up checklists

### 4. Workstream Layer

The workstream layer coordinates bounded project execution.

Expected artifacts:

- workstream artifacts in `projects/workstreams/`
- milestone plans in `projects/milestones/`
- daily or phase sections inside active workstreams
- agent task queues
- carryover notes

### 5. Wiki Control Layer

The control layer helps humans and agents navigate and audit the repository.

Expected artifacts:

- `meta/index.md` as the navigation catalog
- `meta/log.md` as the append-only activity log
- `meta/source-registry.md` as the source inventory and tier tracker
- templates for durable artifact creation

### 6. Issue And Agent Collaboration Layer

GitHub issues, projects, branches, and pull requests make work visible.

Expected artifacts:

- workstream issues
- agent task issues
- source ingest issues
- review issues
- decision issues
- maintenance issues

Agents should leave a trace: changed files, issue comments, logs, and verification notes.

## Operating Loop

```text
goal or question
  -> workstream or issue
  -> source registration
  -> source decomposition
  -> source map or summary
  -> knowledge note or decision
  -> review
  -> follow-up task
  -> log and index update
```

## Directory Contract

```text
AGENTS.md
meta/
raw/
knowledge/
reviews/
projects/
docs/
tools/
```

Add new folders only when they represent a repeated workflow or durable artifact type.
