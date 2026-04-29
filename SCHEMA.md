# Hermes Memory Wiki — Schema Reference

This file is the canonical page-authoring reference for the Hermes Memory Wiki. Every compiled page must conform to these rules. The `hermes memory-wiki lint` command enforces all requirements marked **required**.

---

## Frontmatter

Every compiled page (under `entities/`, `concepts/`, `decisions/`, `incidents/`, `queries/`) **must** begin with a YAML frontmatter block.

```yaml
---
title: Page Title                      # required — human-readable name of the page
created: YYYY-MM-DD                    # required — ISO date the page was first written
updated: YYYY-MM-DD                    # required — ISO date of the last meaningful change
type: entity | concept | decision | incident | query   # required — see Type below
scope: hermes | oracle | alfred | triad | project | user  # optional — who this is relevant to
status: active | stale | superseded | stub             # required — lifecycle status
tags: [tag1, tag2]                     # optional — from the canonical tag list below
sources: [raw/sessions/foo.md]         # optional — raw source files this page was compiled from
---
```

### Required fields

All five of these must be present and non-empty. The linter raises an **error** if any is missing:

| Field | Format | Notes |
|---|---|---|
| `title` | free text | Short human-readable name |
| `created` | `YYYY-MM-DD` | Date page was authored |
| `updated` | `YYYY-MM-DD` | Update on every meaningful edit |
| `type` | enum (see below) | Content type of this page |
| `status` | enum (see below) | Current lifecycle status |

### Optional fields

| Field | Format | Notes |
|---|---|---|
| `scope` | enum (see below) | Which agent or context this is relevant to |
| `tags` | YAML list | Must only use tags from the canonical list below |
| `sources` | YAML list | Relative paths to raw source files |
| `stub` | `true` | Set to suppress the "two outbound wikilinks" requirement |

---

## Type enum

| Value | Where it lives | When to use |
|---|---|---|
| `entity` | `entities/` | A specific named thing: person, agent, project, tool |
| `concept` | `concepts/` | A pattern, principle, preference, workflow, or architecture decision |
| `decision` | `decisions/` | A dated architecture decision record (ADR) |
| `incident` | `incidents/` | A post-mortem or description of a notable failure |
| `query` | `queries/` | A research output or one-off investigation |

The `type` value must match the top-level directory. A page with `type: concept` must live under `concepts/`. The linter does not currently enforce the directory/type correspondence (it only checks that `type` is non-empty), but this convention must be followed by authors.

---

## Status enum

| Value | Meaning |
|---|---|
| `active` | Current and accurate |
| `stale` | Likely outdated; needs review before use |
| `superseded` | Replaced by a newer page; keep for history |
| `stub` | Auto-promoted scaffold, content not yet filled in |

Newly promoted pages start as `stub`. Change to `active` once you have filled in the content and verified it with lint.

---

## Scope enum

| Value | Meaning |
|---|---|
| `hermes` | Specific to the Hermes gateway agent |
| `oracle` | Specific to the Oracle vault coordinator |
| `alfred` | Specific to the Alfred system coordinator |
| `triad` | Shared across Hermes, Oracle, and Alfred |
| `project` | Specific to a single project |
| `user` | Specific to the human user (Ayaz) |

---

## Tags

Tags must be from this canonical list. Unknown tags generate a **warning** from the linter. To add a new tag, update `SCHEMA.md` and the `SCHEMA.md` that `hermes memory-wiki init` seeds inside the wiki.

```
identity
preference
workflow
memory
artifact
project
handoff
hermes
oracle
alfred
triad
vault
system
incident
decision
pitfall
cron
telegram
skill
architecture
promotion
```

---

## Wikilinks

Every compiled page must have at least **two outbound wikilinks** (`[[rel/path/to/page]]`) unless the page has `stub: true` in its frontmatter. The linter raises an **error** for broken wikilinks (targets that have no matching `.md` file on disk).

Format accepted:
- `[[entities/agents/hermes]]` — bare path, no extension
- `[[entities/agents/hermes|Hermes Agent]]` — piped label (linter resolves via the left side)

Do not include the `.md` extension in wikilinks.

---

## index.md

Every compiled page must have an entry in `index.md`. The linter raises an **error** if a page is absent from the index. Accepted formats:

```markdown
- [[entities/agents/hermes]] — Hermes — messenger / rhythm-keeper agent
- [[entities/agents/hermes|Hermes Agent]] — Hermes — messenger / rhythm-keeper agent
```

Both bare and piped wikilink forms are recognised. The entry must include a brief description after the ` — ` separator (used as a search bonus by `hermes memory-wiki search`).

---

## log.md

`log.md` is **append-only**. Every operation (init, ingest, lint, promote, query, archive) must append an entry in this format:

```markdown
## [YYYY-MM-DD] action | subject
```

Never truncate, reorganize, or rewrite log.md. It is an audit trail.

---

## Raw sources

Files under `raw/` are **immutable**. They are write-once inputs:

- `raw/sessions/` — session transcripts, exported chat logs
- `raw/artifacts/` — files ingested via `hermes memory-wiki ingest-artifact`
- `raw/vault/` — vault exports (Obsidian markdown, etc.)
- `raw/handoffs/` — inter-agent handoff documents
- `raw/sources/` — other inputs that don't fit the above

Do not edit raw files after they are placed. If a raw source is superseded, add a new file rather than modifying the old one.

---

## Page size

The linter issues a **warning** when a compiled page exceeds 200 lines. At that point, consider splitting the page into two more focused pages linked by wikilinks.

---

## Page authoring thresholds

Create or update a page when any of the following is true:

- The fact would change future agent behavior.
- The item appears in 2+ sessions or raw sources.
- The item is central to one source (a correction, implementation plan, or incident report).
- The answer would be painful to reconstruct from chat history alone.

Do not create pages for session-scoped insights or facts that are obvious from the code.

---

## Secrets

**Never store secrets in any wiki file.** This includes API keys, tokens, passwords, credentials, private keys, and bearer tokens. The `memory_wiki_ingest_artifact` tool actively scans filenames and file contents for secret patterns and refuses to ingest files that match.
