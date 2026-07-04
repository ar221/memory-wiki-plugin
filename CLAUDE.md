# memory-wiki-plugin

A compiled-wiki memory plugin for [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent). Raw session sources are compiled by the LLM into synthesized markdown pages; the LLM reads the compiled pages, not the raw dumps. Pattern: raw sources → LLM-maintained compiled wiki → schema/lint discipline → structured recall.

## Stack
- Python, stdlib-based. 55 tests (pytest), all passing.
- Subclasses hermes-agent's `MemoryProvider`; installed into a hermes-agent clone via `install.sh`.

## Layout
- `scripts/memory_wiki/` — core: `paths.py` (honours `HERMES_HOME`), `init.py`, `lint.py` (6 checks), `search.py`, `ingest_artifact.py`, `promote.py` (promotion pipeline).
- `plugins/memory/wiki/__init__.py` — `WikiMemoryProvider` (detects preference signals + plans, files candidates).
- `tools/memory_wiki_tool.py` — 4 agent-callable tools + registry.
- `hermes_cli/memory_wiki.py` — CLI dispatcher (6 subcommands).
- `SCHEMA.md` — canonical page-authoring reference; `install.sh` — copies files into a hermes-agent clone.
- `tests/` — 55 tests, all via `_hermetic_environment` fixture (never touches real `~/.hermes`).

## Entrypoint
- Install: `./install.sh /path/to/your/hermes-agent` (validates git repo, copies plugin files) + two manual source patches (see README §3).
- Promote: `hermes memory-wiki promote` (reviews candidates, generates stub pages).
- Tests: `pytest` (hermetic; `HERMES_HOME` redirected per-test).

## Status
- Branch: `main`. Extracted from local fork at `~/.hermes/hermes-agent/` (7-phase implementation). Working tree has uncommitted work — add-only.

## Conventions
Inherits ~/CLAUDE.md (Alfred). Page schema authority is `SCHEMA.md`. Repo-specific overrides here.
