#!/usr/bin/env bash
# install.sh — Copy memory-wiki plugin files into an existing hermes-agent clone.
#
# Usage:
#   ./install.sh /path/to/hermes-agent
#
# The script mirrors every plugin file to its canonical path inside the target
# clone and then prints the two manual integration steps with exact code.

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

if [[ $# -ne 1 ]]; then
    echo "Error: expected exactly one argument." >&2
    echo "Usage: $0 /path/to/hermes-agent" >&2
    exit 1
fi

TARGET="$1"

if [[ ! -d "$TARGET" ]]; then
    echo "Error: '$TARGET' is not a directory." >&2
    exit 1
fi

if [[ ! -d "$TARGET/.git" ]]; then
    echo "Error: '$TARGET' does not appear to be a git repository (no .git directory found)." >&2
    exit 1
fi

echo "Installing memory-wiki plugin into: $TARGET"
echo ""

# ---------------------------------------------------------------------------
# Files to install (source path relative to plugin root → dest relative to TARGET)
# ---------------------------------------------------------------------------

FILES=(
    "scripts/__init__.py"
    "scripts/memory_wiki/__init__.py"
    "scripts/memory_wiki/paths.py"
    "scripts/memory_wiki/init.py"
    "scripts/memory_wiki/lint.py"
    "scripts/memory_wiki/search.py"
    "scripts/memory_wiki/ingest_artifact.py"
    "scripts/memory_wiki/promote.py"
    "plugins/memory/wiki/__init__.py"
    "tools/memory_wiki_tool.py"
    "hermes_cli/memory_wiki.py"
    "tests/scripts/__init__.py"
    "tests/scripts/test_memory_wiki_lint.py"
    "tests/scripts/test_memory_wiki_promote.py"
    "tests/hermes_cli/test_memory_wiki_cli.py"
    "tests/plugins/memory/test_wiki_provider.py"
    "tests/tools/test_memory_wiki_tool.py"
)

for rel in "${FILES[@]}"; do
    src="$PLUGIN_DIR/$rel"
    dest="$TARGET/$rel"
    dest_dir="$(dirname "$dest")"

    mkdir -p "$dest_dir"
    cp "$src" "$dest"
    echo "  copied  $rel"
done

echo ""
echo "All plugin files installed."
echo ""

# ---------------------------------------------------------------------------
# Manual integration steps
# ---------------------------------------------------------------------------

cat <<'STEPS'
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANUAL INTEGRATION — two patches required in hermes-agent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

────────────────────────────────────────────────────────────────────────────
PATCH 1 — hermes_cli/main.py
────────────────────────────────────────────────────────────────────────────

Add the following near the other cmd_* functions:

    def cmd_memory_wiki(args):
        """Memory wiki management."""
        import sys
        from hermes_cli.memory_wiki import memory_wiki_command
        rc = memory_wiki_command(args)
        if rc is not None and rc != 0:
            sys.exit(rc)

Then add the following in the subparsers block (e.g. after cron_parser.set_defaults):

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

────────────────────────────────────────────────────────────────────────────
PATCH 2 — toolsets.py
────────────────────────────────────────────────────────────────────────────

Add the following entry to the TOOLSETS dict:

    "memory_wiki": {
        "description": "Hermes compiled memory wiki tools — search, read, ingest, and lint wiki pages",
        "tools": ["memory_wiki_search", "memory_wiki_read", "memory_wiki_ingest_artifact", "memory_wiki_lint"],
        "includes": []
    },

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEPS
