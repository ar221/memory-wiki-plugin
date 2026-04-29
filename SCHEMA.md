# Hermes Memory Wiki Schema

## Domain
Compiled memory for Hermes/Ayaz OS: user preferences, agent identities, project state, workflows, decisions, incidents, artifacts, and cross-domain knowledge.

## Conventions
- Raw sources under `raw/` are immutable.
- Compiled pages live under `entities/`, `concepts/`, `decisions/`, `incidents/`, or `queries/`.
- Every compiled page uses YAML frontmatter.
- Every compiled page has at least two outbound `[[wikilinks]]` unless explicitly marked `stub: true`.
- Every new or updated compiled page must be listed in `index.md`.
- Every ingest/query/lint/promotion must append to `log.md`.
- Prefer concise pages; split pages over ~200 lines.
- Never store secrets.

## Frontmatter

```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | decision | incident | query
scope: hermes | oracle | alfred | triad | project | user
status: active | stale | superseded | stub
tags: []
sources: []
---
```

## Tags
- identity
- preference
- workflow
- memory
- artifact
- project
- handoff
- hermes
- oracle
- alfred
- triad
- vault
- system
- incident
- decision
- pitfall
- cron
- telegram
- skill
- architecture
- promotion

## Page thresholds
Create or update a page when:
- The fact affects future behavior.
- The item appears in 2+ sessions/sources.
- The item is central to one source, correction, implementation plan, or incident.
- The answer would be painful to reconstruct from chat history.
