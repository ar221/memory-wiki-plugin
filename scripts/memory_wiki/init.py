"""Initialize (or no-op) the Hermes Memory Wiki directory tree.

Idempotent: if the tree already exists this script does nothing.

Usage:
    python -m scripts.memory_wiki.init
"""

from __future__ import annotations

from pathlib import Path

from scripts.memory_wiki.paths import wiki_root

# ---------------------------------------------------------------------------
# Template text — embedded so the script is self-contained on first run.
# Derived from the canonical files seeded in Phase B.
# ---------------------------------------------------------------------------

_SCHEMA_MD = """\
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
"""

_INDEX_MD = """\
# Hermes Memory Wiki Index

> Read this first before querying or updating the memory wiki.
> Last updated: {date} | Total compiled pages: 0

## People

## Agents

## Projects

## Tools

## Preferences

## Workflows

## Architecture

## Pitfalls

## Decisions

## Incidents

## Queries
"""

_LOG_MD = """\
# Hermes Memory Wiki Log

> Append-only chronological log.
> Format: `## [YYYY-MM-DD] action | subject`
> Actions: init, ingest, update, query, lint, promote, archive

"""

# ---------------------------------------------------------------------------
# Directory structure
# ---------------------------------------------------------------------------

_SUBDIRS: list[str] = [
    "raw/sessions",
    "raw/artifacts",
    "raw/vault",
    "raw/handoffs",
    "raw/sources",
    "entities/people",
    "entities/agents",
    "entities/projects",
    "entities/tools",
    "concepts/preferences",
    "concepts/workflows",
    "concepts/architecture",
    "concepts/pitfalls",
    "decisions",
    "incidents",
    "queries",
    "_meta/lint-reports",
    "_meta/promotion-reports",
]


def init(root: Path | None = None) -> None:
    """Create the memory-wiki tree and meta files if they don't exist.

    Parameters
    ----------
    root:
        Override the wiki root (defaults to ``wiki_root()``).  Useful in
        tests that supply a custom path.
    """
    from datetime import date

    if root is None:
        root = wiki_root()

    root.mkdir(parents=True, exist_ok=True)

    for subdir in _SUBDIRS:
        (root / subdir).mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()

    # SCHEMA.md
    schema = root / "SCHEMA.md"
    if not schema.exists():
        schema.write_text(_SCHEMA_MD, encoding="utf-8")

    # index.md
    index = root / "index.md"
    if not index.exists():
        index.write_text(_INDEX_MD.format(date=today), encoding="utf-8")

    # log.md
    log = root / "log.md"
    if not log.exists():
        log.write_text(
            _LOG_MD + f"## [{today}] init | Hermes Memory Wiki initialized\n",
            encoding="utf-8",
        )


def main() -> None:
    root = wiki_root()
    init(root)
    print(f"Memory wiki ready at: {root}")


if __name__ == "__main__":
    main()
