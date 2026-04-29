# memory-wiki-plugin

Karpathy-style LLM wiki memory for [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent). Extracted from the local fork at `~/.hermes/hermes-agent/` (merge commit `93724c5d`, 7 implementation phases).

---

## 1. What this is

Standard LLM memory systems either dump raw session transcripts into context (verbose, incoherent) or rely on opaque vector stores (black-box, hard to audit). This plugin takes a third path, inspired by Andrej Karpathy's practice of maintaining a hand-curated wiki of distilled knowledge: **raw session sources are compiled by the LLM into synthesized markdown pages, and the LLM reads the compiled pages rather than the raw dumps**.

The pattern in one sentence: raw sources → LLM-maintained compiled wiki → schema/lint discipline → structured recall.

Benefits over raw recall:
- **Coherence**: compiled pages are authored by an LLM that already understood the context, so they read like encyclopedia entries rather than chat fragments.
- **Token efficiency**: a 200-line compiled concept page replaces many kilobytes of session transcript.
- **Auditability**: every page is a plain markdown file on disk, versioned with git, readable by humans.
- **Schema discipline**: the lint command enforces frontmatter and cross-referencing rules, keeping the corpus machine-readable.

The promotion pipeline bridges the gap between ephemeral session signals and durable wiki knowledge: the `WikiMemoryProvider` detects preference signals and implementation plans during live sessions and files them as candidates; `hermes memory-wiki promote` reviews candidates and generates stub pages for author review.

---

## 2. Repository layout

```
memory-wiki-plugin/
├── SCHEMA.md                                  # Wiki schema — source of truth for all page authors
├── install.sh                                 # Copies files into a hermes-agent clone
├── scripts/
│   ├── __init__.py
│   └── memory_wiki/
│       ├── __init__.py
│       ├── paths.py           # Path helpers (honours HERMES_HOME)
│       ├── init.py            # Idempotent wiki tree initialiser
│       ├── lint.py            # Schema linter (6 checks, JSON findings + markdown report)
│       ├── search.py          # Keyword search with index.md bonus weighting
│       ├── ingest_artifact.py # Copy artifact into raw/artifacts/ with date prefix
│       └── promote.py        # Promotion pipeline (parse_since, load, classify, propose, apply)
├── plugins/
│   └── memory/
│       └── wiki/
│           ├── __init__.py    # WikiMemoryProvider (MemoryProvider subclass)
│           └── plugin.yaml    # Plugin manifest
├── tools/
│   └── memory_wiki_tool.py   # 4 agent-callable tools + registry
├── hermes_cli/
│   └── memory_wiki.py        # CLI dispatcher (6 subcommands)
└── tests/
    ├── scripts/
    │   ├── test_memory_wiki_lint.py     # 12 tests: lint checks, ingest, report collision
    │   └── test_memory_wiki_promote.py  # 13 tests: parse_since, load, classify, apply, report
    ├── hermes_cli/
    │   └── test_memory_wiki_cli.py      # 8 tests: each subcommand via Namespace
    ├── plugins/
    │   └── memory/
    │       └── test_wiki_provider.py    # 11 tests: availability, prefetch, sync_turn, session end
    └── tools/
        └── test_memory_wiki_tool.py     # 11 tests: search, read, ingest (security), lint
```

All 55 tests use the `_hermetic_environment` fixture from hermes-agent's `conftest.py`, which redirects `HERMES_HOME` to a per-test tempdir so no test ever touches the real `~/.hermes`.

---

## 3. Install

### Step A — run the install script

```bash
git clone https://github.com/ar221/memory-wiki-plugin.git
cd memory-wiki-plugin
./install.sh /path/to/your/hermes-agent
```

The script validates that the target is a git repository, then mirrors every plugin file to its canonical path. It prints each copied path.

### Step B — two manual patches to hermes-agent

The install script cannot safely patch Python source files automatically. Apply the two patches below by hand.

#### Patch 1 — `hermes_cli/main.py`

Add the following near the other `cmd_*` functions:

```python
def cmd_memory_wiki(args):
    """Memory wiki management."""
    import sys
    from hermes_cli.memory_wiki import memory_wiki_command
    rc = memory_wiki_command(args)
    if rc is not None and rc != 0:
        sys.exit(rc)
```

Add the following in the subparsers block (e.g. after `cron_parser.set_defaults`):

```python
mw_parser = subparsers.add_parser(
    "memory-wiki",
    help="Manage the Hermes memory wiki",
    description="Compiled markdown memory wiki for Hermes/Ayaz OS",
)
mw_subparsers = mw_parser.add_subparsers(dest="memory_wiki_command")
mw_subparsers.add_parser("init", help="Initialize or verify the memory wiki")
mw_subparsers.add_parser("path", help="Print the memory wiki root path")
mw_subparsers.add_parser("lint", help="Lint compiled pages for schema violations")
mw_ingest = mw_subparsers.add_parser("ingest-artifact", help="Copy an artifact into raw/artifacts/ and log it")
mw_ingest.add_argument("path", help="Path to the artifact file to ingest")
mw_ingest.add_argument("--note", default="", help="Optional note appended to the log entry")
mw_search = mw_subparsers.add_parser("search", help="Keyword search over compiled wiki pages")
mw_search.add_argument("query", help="Search terms")
mw_search.add_argument("--limit", type=int, default=5, help="Max results (default: 5)")
mw_promote = mw_subparsers.add_parser("promote", help="Promote candidates from _meta/promotion-reports/ into compiled pages")
mw_promote.add_argument("--since", default="24h", help="Time window: e.g. '24h', '7d', 'today' (default: 24h)")
mw_promote.add_argument("--auto-approve", action="store_true", dest="auto_approve", help="Skip the confirmation gate")
mw_parser.set_defaults(func=cmd_memory_wiki)
```

#### Patch 2 — `toolsets.py`

Add the `"memory_wiki"` entry to the `TOOLSETS` dict:

```python
"memory_wiki": {
    "description": "Hermes compiled memory wiki tools — search, read, ingest, and lint wiki pages",
    "tools": ["memory_wiki_search", "memory_wiki_read", "memory_wiki_ingest_artifact", "memory_wiki_lint"],
    "includes": []
},
```

---

## 4. CLI usage

After both patches, the `hermes memory-wiki` top-level command is available with 6 subcommands.

### `hermes memory-wiki init`

Create (or verify) the wiki directory tree at `<HERMES_HOME>/memory-wiki/`. Idempotent — safe to run multiple times; existing files are never overwritten.

```bash
hermes memory-wiki init
# Memory wiki ready at: /home/user/.hermes/memory-wiki
```

Creates: all subdirectories, `SCHEMA.md`, `index.md`, and `log.md`.

### `hermes memory-wiki path`

Print the wiki root path. Respects the `HERMES_HOME` environment variable and any profile-aware logic in `hermes_constants.get_hermes_home()`.

```bash
hermes memory-wiki path
# /home/user/.hermes/memory-wiki
```

### `hermes memory-wiki lint`

Lint all compiled pages (under `entities/`, `concepts/`, `decisions/`, `incidents/`, `queries/`) for schema violations. Prints a JSON findings list to stdout and saves a markdown report to `_meta/lint-reports/YYYY-MM-DD.md`. Appends a summary line to `log.md`.

Exit code: **0** if no errors (warnings are allowed), **1** if any errors were found.

```bash
hermes memory-wiki lint
# [...JSON findings...]
# Report saved: /home/user/.hermes/memory-wiki/_meta/lint-reports/2026-04-29.md
# Summary: 0 error(s), 2 warning(s)
```

Same-day re-runs produce `YYYY-MM-DD-2.md`, `YYYY-MM-DD-3.md`, etc. — no silent overwrites.

### `hermes memory-wiki ingest-artifact <path> [--note "..."]`

Copy a file into `raw/artifacts/` with a `YYYY-MM-DD-` prefix and log the operation. A compiled page update is still required after ingestion — the ingest command only handles the raw import step.

```bash
hermes memory-wiki ingest-artifact ~/Downloads/research-notes.md --note "Cole Medin RAG paper summary"
# Ingested: /home/user/.hermes/memory-wiki/raw/artifacts/2026-04-29-research-notes.md
# Compiled page update still required.
```

Collision avoidance: if the destination exists, a `-2`, `-3`, ... suffix is appended.

### `hermes memory-wiki search <query> [--limit N]`

Keyword search across all compiled pages. Scores by term frequency; titles and `index.md` one-liner descriptions receive a bonus weight (2x). Returns up to `--limit` results (default 5), sorted by score.

```bash
hermes memory-wiki search "artifact retention workflow" --limit 3
# [4] concepts/artifact-retention.md — Artifact Retention | How session outputs are preserved
# [2] entities/agents/hermes.md — Hermes | Messenger / rhythm-keeper agent
# [1] concepts/workflows/log-sync.md — Log Sync Workflow
```

### `hermes memory-wiki promote [--since 24h|7d|today] [--auto-approve]`

Review promotion candidates from `_meta/promotion-reports/` and generate compiled page stubs. Candidates are written there by the `WikiMemoryProvider.sync_turn` heuristics during live sessions.

```bash
hermes memory-wiki promote --since 24h
# Found 3 candidate(s) across 2 topic(s):
#   [preference] 2 candidate(s) → create concepts/preferences/2026-04-29-from-candidates.md
#   [decision]   1 candidate(s) → create decisions/2026-04-29-from-candidates.md
# Applied 2 page update(s):
#   concepts/preferences/2026-04-29-from-candidates.md
#   decisions/2026-04-29-from-candidates.md

# With auto-approve (skip confirmation gate):
hermes memory-wiki promote --since 7d --auto-approve
```

The `--since` flag accepts: `Nh` (N hours ago), `Nd` (N days ago), or `today` (since midnight UTC). If more than 3 topic groups are proposed, the CLI asks for confirmation unless `--auto-approve` is passed.

---

## 5. The wiki schema (SCHEMA.md)

All compiled pages **must** follow `SCHEMA.md` at the repo root. The `lint` command enforces it. Key rules:

- **`raw/` is immutable** — never edit files under `raw/`. Raw sources are write-once inputs from sessions, artifact ingests, vault exports, and handoffs.
- **Compiled pages live under `entities/`, `concepts/`, `decisions/`, `incidents/`, `queries/`** — no compiled content belongs anywhere else in the tree.
- **Every compiled page needs YAML frontmatter** with these required fields:
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
- **Every compiled page must have at least 2 outbound `[[wikilinks]]`** unless the page has `stub: true` in its frontmatter. The linter checks this.
- **Every new or updated page must appear in `index.md`** — referenced as `[[rel/path/without/ext]]` or `[[rel/path|Label]]` (both forms are recognised by the linter).
- **Every ingest, query, lint, and promote operation must append to `log.md`** — the log is append-only and chronological.
- **Pages over ~200 lines should be split** — the linter issues a warning at 201+ lines.
- **Tags must be from the canonical list in SCHEMA.md** — unknown tags trigger a warning.
- **Never store secrets** in any wiki file.

The allowed tag vocabulary covers: `identity`, `preference`, `workflow`, `memory`, `artifact`, `project`, `handoff`, `hermes`, `oracle`, `alfred`, `triad`, `vault`, `system`, `incident`, `decision`, `pitfall`, `cron`, `telegram`, `skill`, `architecture`, `promotion`.

---

## 6. Agent toolset

The `memory_wiki` toolset exposes 4 tools to the Hermes agent. To activate:

```bash
hermes config set toolsets.enabled memory_wiki
```

(or however your Hermes installation enables toolsets — consult your `toolsets.py`).

All tools return JSON strings. Errors use `tool_error()` from `tools.registry` and always include an `"error"` key.

### `memory_wiki_search(query, limit=5)`

Keyword search over compiled wiki pages. Returns:
```json
{
  "results": [
    {"path": "concepts/preferences/foo.md", "score": 7, "title": "Foo", "description": "One-liner from index.md"}
  ]
}
```

### `memory_wiki_read(path)`

Read a compiled page by its relative path (e.g. `"entities/agents/hermes"` or `"concepts/handoff-protocol"`). Strips `.md` if provided. Returns:
```json
{"path": "entities/agents/hermes", "content": "---\ntitle: Hermes\n..."}
```

**Security**: path-traversal is blocked at the resolved-path level. Only files under the five compiled-page directories (`entities/`, `concepts/`, `decisions/`, `incidents/`, `queries/`) can be read.

### `memory_wiki_ingest_artifact(source_path, note="")`

Copy a file to `raw/artifacts/` and log the ingest. Returns:
```json
{"success": true, "dest": "/home/user/.hermes/memory-wiki/raw/artifacts/2026-04-29-notes.md", "note": "Compiled page update still required."}
```

**Security rules**:
- Source file must be under one of the allowed roots: `~/.hermes/artifacts/`, `~/.hermes/cron/output/`, `~/Downloads/`, `~/Documents/`, `~/Desktop/`. Files from any other location are rejected.
- Filenames containing `auth`, `secret`, `token`, `password`, `credential`, or `.env` are rejected (name heuristic).
- The first 4KB of the file is scanned for credential patterns (GitHub tokens, `sk-*` API keys, Bearer tokens, PEM headers, `password: value` patterns). Files matching any pattern are rejected. Files over 50KB skip the content scan (name-only check applies).

### `memory_wiki_lint()`

Run the full linter. Returns:
```json
{"errors": 0, "warnings": 2, "findings": [...]}
```

---

## 7. MemoryProvider plugin

The `plugins/memory/wiki/` directory provides a `WikiMemoryProvider` that Hermes loads when `memory.provider` is set to `wiki`.

To enable:
```bash
hermes config set memory.provider wiki
```

`WikiMemoryProvider` implements 5 lifecycle hooks:

### `initialize(session_id, **kwargs)`

Resolves the wiki root from `kwargs["hermes_home"]` or `hermes_constants.get_hermes_home()`. Records whether this is a primary session or a subagent context (`kwargs["agent_context"]`). Subagent contexts skip `sync_turn` writes to avoid promotion noise from parallel workers.

### `system_prompt_block()`

Returns a static one-paragraph notice injected into the system prompt when the wiki's `index.md` exists. Tells the LLM to prefer compiled wiki pages over raw transcript recall and lists the four available tools.

### `prefetch(query, session_id="")`

Called with the first user message. Runs a keyword search with `limit=3` and returns a brief markdown block of the top results, prepended to the conversation context. Returns an empty string if the wiki doesn't exist or search finds nothing.

### `sync_turn(user_content, assistant_content, session_id="")`

Called after every turn in primary sessions. Scans the combined user+assistant text for two classes of durable signal:

1. **Heuristic phrases**: `"remember this"`, `"don't do that"`, `"we decided"`, `"implementation plan"`
2. **Durable preference bigrams**: `always/never` followed by an action verb (`use`, `run`, `do`, `make`, `keep`, `set`, `call`, `write`, `push`, `commit`, `skip`, `avoid`, `prefer`)

If a signal fires, writes a candidate file to `_meta/promotion-reports/YYYY-MM-DD-candidate-<sid>-<ts>.md` containing the trigger, 500-char user excerpt, and 500-char assistant excerpt.

### `on_session_end(messages)`

If the session has 5 or more messages and is a primary context, writes a session summary candidate to `_meta/promotion-reports/YYYY-MM-DD-session-<sid>.md` with the first and last user messages.

### `on_pre_compress(messages)`

Returns a brief reminder string telling the compressor not to discard decisions or preferences, so they survive context compression.

### `get_tool_schemas()` / `shutdown()`

Returns `[]` (tools are registered via the toolset, not by the provider) and is a no-op respectively.

---

## 8. Promotion pipeline

The promotion pipeline converts ephemeral session signals into durable wiki pages. There is no LLM in the loop during promotion — it is pure text manipulation. The LLM author fills in content after stubs are created.

**Full flow:**

1. During live sessions, `WikiMemoryProvider.sync_turn` detects signals and writes candidate files to `~/.hermes/memory-wiki/_meta/promotion-reports/YYYY-MM-DD-candidate-*.md`. At session end, `on_session_end` may write an additional summary candidate.

2. Run `hermes memory-wiki promote --since 24h` (or another window) to collect and review candidates:
   - `parse_since` converts the `--since` string to a UTC cutoff datetime.
   - `load_candidates` reads all `.md` files from `_meta/promotion-reports/` whose `Date:` header is on or after the cutoff. Files whose names end with `-promotion.md` (output reports from prior runs) are skipped.
   - `classify_candidates` groups candidates by topic using keyword heuristics: `"decided"/"decision"` → decision, `"broke"/"bug"/"error"` → incident, `"workflow"/"process"/"how to"` → workflow, `"project"/"campaign"/"task"` → project, everything else → preference.
   - `propose_updates` builds a proposal per topic group. For each group it runs a wiki search with the first candidate as the query; if the top result scores ≥ 3 and lives in the topic directory, it proposes an **update** to that existing page (append). Otherwise it proposes a **create** (new stub page with frontmatter).
   - If more than 3 topic groups are proposed, the CLI asks for interactive confirmation. Pass `--auto-approve` to bypass.
   - `apply_proposals` writes the changes. Creates parent directories as needed. Avoids overwriting by appending a counter suffix to the filename. Updates `index.md` for new pages. Appends to `log.md` for each change.
   - `write_promotion_report` writes a summary to `_meta/promotion-reports/YYYY-MM-DD-promotion.md`.

3. Open the newly created stub pages and fill in the content. The stubs have valid frontmatter with `status: stub` — change to `status: active` when complete.

4. Run `hermes memory-wiki lint` to verify the new pages meet schema requirements.

**Gate**: the CLI asks for confirmation when more than 3 topic groups are proposed. This prevents a single noisy session from generating dozens of stubs. Use `--auto-approve` in non-interactive cron contexts.

---

## 9. Directory structure of a live wiki

The wiki lives at `<HERMES_HOME>/memory-wiki/` (default: `~/.hermes/memory-wiki/`).

```
~/.hermes/memory-wiki/
├── SCHEMA.md                          # canonical page-authoring rules
├── index.md                           # master page index — lists every compiled page
├── log.md                             # append-only operation log
├── raw/                               # immutable source files (never edit)
│   ├── sessions/                      # session transcripts, exported chat logs
│   ├── artifacts/                     # files ingested via ingest-artifact
│   ├── vault/                         # vault exports (Obsidian markdown, etc.)
│   ├── handoffs/                      # inter-agent handoff documents
│   └── sources/                       # other raw inputs
├── entities/                          # compiled pages about specific things
│   ├── people/                        # human contacts
│   ├── agents/                        # agent identities (Hermes, Oracle, Alfred, ...)
│   ├── projects/                      # active and completed projects
│   └── tools/                         # scripts, services, integrations
├── concepts/                          # compiled pages about patterns and principles
│   ├── preferences/                   # persistent user/agent preferences
│   ├── workflows/                     # repeatable processes
│   ├── architecture/                  # system design and structural decisions
│   └── pitfalls/                      # known failure modes and how to avoid them
├── decisions/                         # dated architecture decision records (ADRs)
├── incidents/                         # post-mortems and notable failures
├── queries/                           # research outputs, one-off investigations
└── _meta/
    ├── lint-reports/                  # lint output (YYYY-MM-DD.md per run)
    └── promotion-reports/             # session candidates + promotion output files
```

The `index.md` file is the single source of truth for what compiled pages exist. Every compiled page must have a `[[rel/path]]` entry in `index.md`. The linter enforces this.

The `log.md` file is append-only. Every operation (init, ingest, lint, promote, query) appends a dated header line. Never truncate or reorganize it.

---

## 10. Running tests

The tests live alongside their corresponding modules. They require a hermes-agent environment with `conftest.py`'s `_hermetic_environment` fixture, which sets `HERMES_HOME` to a per-test tempdir.

```bash
cd /path/to/hermes-agent

pytest tests/scripts/test_memory_wiki_lint.py \
       tests/scripts/test_memory_wiki_promote.py \
       tests/hermes_cli/test_memory_wiki_cli.py \
       tests/plugins/memory/test_wiki_provider.py \
       tests/tools/test_memory_wiki_tool.py \
       -v
```

Expected: **55 tests, all pass**.

To run only the memory-wiki tests as a group:

```bash
pytest tests/ -k "memory_wiki" -v
```

Test coverage by module:

| File | Tests | What is covered |
|---|---|---|
| `test_memory_wiki_lint.py` | 12 | Clean wiki passes, missing frontmatter, missing required fields, broken wikilinks, missing from index, piped wikilink in index, page-too-long warning, report file, no-overwrite on same-day re-run, ingest, ingest collision |
| `test_memory_wiki_promote.py` | 13 | `parse_since` (hours/days/today), date filter, classify (decision/workflow/preference), `apply_proposals` (create + update), no candidates, skip output files, `propose_updates` keys, report collision |
| `test_memory_wiki_cli.py` | 8 | `path`, `init`, `lint` (clean exit 0, dirty exit 1), `ingest-artifact`, `search`, no-subcommand usage |
| `test_wiki_provider.py` | 11 | `is_available`, `initialize`, `system_prompt_block`, `prefetch` (results + empty), `sync_turn` (writes candidate + skips subagent), `on_session_end`, `get_tool_schemas`, `on_pre_compress` |
| `test_memory_wiki_tool.py` | 11 | `search` (results + no wiki), `read` (existing + nonexistent + traversal + no wiki), `ingest_artifact` (success + secret rejected + credential content rejected + disallowed root), `lint` (clean + no wiki) |

---

## License

Extracted from [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent). See that project's license for terms.
