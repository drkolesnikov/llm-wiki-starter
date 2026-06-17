# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` resolves it automatically when run inside a clone. Note: the local `origin` URL still points at the project's former owner, which GitHub redirects to the canonical `drkolesnikov/llm-wiki-starter` (same repo, renamed/transferred — `gh repo view` reports `isFork: false`, `parent: null`). `gh` follows the redirect, so issues resolve to `drkolesnikov/llm-wiki-starter`, where #15 and the PRD issues live. Repointing the local origin to the canonical URL is harmless cleanup, not required.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.
