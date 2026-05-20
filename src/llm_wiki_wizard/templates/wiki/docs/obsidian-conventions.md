# Obsidian Conventions

These conventions keep the wiki useful in Obsidian while preserving the repository's normal Markdown and validation rules.

## Link Policy

Canonical internal links are standard Markdown links, such as `[source registry](../meta/source-registry.md)`. Agents should use these for durable navigation because the validator checks them.

Obsidian `[[wikilinks]]` are allowed as secondary graph hints in frontmatter fields such as `linked_concepts` or in short related-concept sections. In v1, the validator tolerates wikilinks by ignoring them; it does not verify that they resolve. Reviews should catch important broken wikilinks manually.

Use both forms only when they serve different jobs:

- Markdown links for file-level navigation and validation.
- Wikilinks for concept browsing, aliases, and graph exploration in Obsidian.

## Frontmatter Fields

Durable wiki pages should keep the existing required fields and add Obsidian-friendly metadata when useful:

- `aliases`: alternate names a human might search for.
- `tags`: lowercase topic or workflow tags.
- `sources`: registered source IDs that support the artifact.
- `source_count`: number of registered source IDs in `sources`.
- `linked_concepts`: concept-level wikilinks for Obsidian graph browsing.
- `linked_reviews`: Markdown paths or issue references for review artifacts.
- `updated`: last material update date.
- `status`: one of the validator-supported statuses.

Keep arrays simple and explicit. Prefer multiline YAML lists when values contain spaces, brackets, or punctuation.

## Graph Hygiene

Knowledge notes should avoid becoming isolated pages. A useful durable note should normally link to at least one of:

- a registered source,
- an active workstream or issue,
- a related note,
- a review,
- a decision.

When a note is incomplete, set `status: needs-review`. When sources disagree, set `status: conflicted` and preserve the disagreement instead of smoothing it into a single claim.

## Attachments And Heavy Files

Do not place heavyweight originals or broad source captures in Obsidian attachment folders by default. Keep heavyweight originals outside normal Git through [raw external storage](../raw/external/README.md), and commit only useful derivatives under [raw derived outputs](../raw/derived/README.md).

Small images or attachments may be added later only when a specific note, review, or decision needs them and the source policy allows it.

## Example

A finished knowledge note should demonstrate the v1 pattern: standard Markdown links for repository navigation, registered source IDs in frontmatter, and optional wikilinks for concepts.
