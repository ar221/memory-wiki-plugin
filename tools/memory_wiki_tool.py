"""Memory Wiki tools for Hermes Agent.

Provides 4 agent-callable tools for searching, reading, ingesting artifacts
into, and linting the compiled Hermes Memory Wiki.

All tools return JSON strings. Errors use tool_error() from tools.registry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from hermes_constants import get_hermes_home

from tools.registry import registry, tool_error

# ---------------------------------------------------------------------------
# Compiled-page directories (mirrors scripts/memory_wiki/{search,lint}.py)
# ---------------------------------------------------------------------------

_COMPILED_DIRS = frozenset(("entities", "concepts", "decisions", "incidents", "queries"))

# Filename substrings that indicate a credential/secret file.
# NOTE: This is a filename-only heuristic — see _looks_like_secret() docstring.
_SECRET_SUBSTRINGS = ("auth", "secret", "token", "password", "credential", ".env")

# Allowlist of source roots for ingest_artifact. Files must be under one of
# these directories to be ingestible. Computed at import time (normal user context).
_INGEST_ALLOWED_ROOTS = (
    Path.home() / ".hermes" / "artifacts",
    Path.home() / ".hermes" / "cron" / "output",
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home() / "Desktop",
)

# Regex to detect common credential patterns in file content.
_CREDENTIAL_CONTENT_RE = re.compile(
    r"(ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{32,}|Bearer\s+[A-Za-z0-9._-]{20,}"
    r"|-----BEGIN [A-Z ]+-+|password\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Tool 1: memory_wiki_search
# ---------------------------------------------------------------------------


def memory_wiki_search(query: str, limit: int = 5) -> str:
    """Search the compiled Hermes memory wiki for pages matching a query.
    Returns top matching pages with scores and titles."""
    root = get_hermes_home() / "memory-wiki"
    if not root.is_dir():
        return tool_error("Memory wiki not found. Run hermes memory-wiki init first.")

    try:
        from scripts.memory_wiki.search import search
        results = search(query, limit=limit, root=root)
    except Exception as exc:
        return tool_error(f"Search failed: {exc}")

    return json.dumps({"results": results})


# ---------------------------------------------------------------------------
# Tool 2: memory_wiki_read
# ---------------------------------------------------------------------------


def memory_wiki_read(path: str) -> str:
    """Read a compiled memory wiki page by its relative path (e.g. 'entities/agents/hermes').
    Strips the .md extension if provided. Returns the page content."""
    root = get_hermes_home() / "memory-wiki"
    if not root.is_dir():
        return tool_error("Memory wiki not found. Run hermes memory-wiki init first.")

    # Strip .md suffix if provided.
    clean_path = path.removesuffix(".md") if path.endswith(".md") else path

    candidate = root / f"{clean_path}.md"

    # Security: path-traversal guard.
    try:
        resolved = candidate.resolve()
        root_resolved = root.resolve()
    except Exception as exc:
        return tool_error(f"Path resolution failed: {exc}")

    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        return tool_error("Path traversal not allowed.")

    # Compiled-dirs guard: only allow reads from known compiled-page directories.
    try:
        parts = resolved.relative_to(root_resolved).parts
        if not parts or parts[0] not in _COMPILED_DIRS:
            return tool_error("Only compiled pages can be read.")
    except ValueError:
        return tool_error("Path traversal not allowed.")

    if not resolved.exists():
        return tool_error(f"Page not found: {path}")

    try:
        content = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return tool_error(f"Could not read page: {exc}")

    return json.dumps({"path": clean_path, "content": content})


# ---------------------------------------------------------------------------
# Tool 3: memory_wiki_ingest_artifact
# ---------------------------------------------------------------------------


def _looks_like_secret(filename: str) -> bool:
    """Return True if the filename looks like a secret/credential file.

    IMPORTANT: This is a filename-only heuristic. It checks the name, not the
    content. Use _contains_credentials() for a lightweight content scan.
    """
    lower = filename.lower()
    return any(sub in lower for sub in _SECRET_SUBSTRINGS)


def _contains_credentials(path: Path) -> bool:
    """Scan first 4KB of file for common credential patterns.

    Name-only checks (_looks_like_secret) are insufficient — a file can carry
    secrets under an innocuous name. This function provides a lightweight
    content-level backstop for files under 50KB.

    Returns False on any OSError (e.g. permission denied) to avoid blocking
    valid ingest on unreadable but harmless files.
    """
    try:
        if path.stat().st_size > 50 * 1024:
            return False  # skip large files — too slow, name-check only
        sample = path.read_bytes()[:4096].decode("utf-8", errors="replace")
        return bool(_CREDENTIAL_CONTENT_RE.search(sample))
    except OSError:
        return False


def memory_wiki_ingest_artifact(path: str, note: str = "") -> str:
    """Copy an artifact file into the memory wiki's raw/artifacts/ directory and log the ingest.
    Returns the destination path. A compiled page update is still required after ingestion."""
    src = Path(path)

    if not src.exists():
        return tool_error(f"File not found: {path}")

    if not src.is_file():
        return tool_error(f"Not a file: {path}")

    # Safety: enforce source allowlist — only files under known safe roots.
    src_resolved = src.resolve()
    if not any(src_resolved.is_relative_to(r.resolve()) for r in _INGEST_ALLOWED_ROOTS):
        return tool_error(
            f"Refusing to ingest: source must be under an allowed directory "
            f"({', '.join(str(r) for r in _INGEST_ALLOWED_ROOTS)})."
        )

    # Safety: refuse credential/secret-looking filenames or content.
    if _looks_like_secret(src.name) or _contains_credentials(src):
        return tool_error("Refusing to ingest file: looks like a secret or credential file.")

    root = get_hermes_home() / "memory-wiki"

    try:
        from scripts.memory_wiki.ingest_artifact import ingest
        dest = ingest(src=src, note=note or None, root=root)
    except Exception as exc:
        return tool_error(f"Ingest failed: {exc}")

    return json.dumps({
        "success": True,
        "dest": str(dest),
        "note": "Compiled page update still required.",
    })


# ---------------------------------------------------------------------------
# Tool 4: memory_wiki_lint
# ---------------------------------------------------------------------------


def memory_wiki_lint() -> str:
    """Run the memory wiki linter. Returns findings as JSON with error/warning counts."""
    root = get_hermes_home() / "memory-wiki"
    if not root.is_dir():
        return tool_error("Memory wiki not found.")

    try:
        from scripts.memory_wiki.lint import run
        findings = run(root=root)
    except Exception as exc:
        return tool_error(f"Lint failed: {exc}")

    error_count = sum(1 for f in findings if f.get("severity") == "error")
    warning_count = sum(1 for f in findings if f.get("severity") == "warning")

    return json.dumps({
        "errors": error_count,
        "warnings": warning_count,
        "findings": findings,
    })


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SEARCH_SCHEMA = {
    "name": "memory_wiki_search",
    "description": (
        "Search the compiled Hermes memory wiki for pages matching a query. "
        "Returns top matching pages with scores, titles, and one-liner descriptions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query string. Keyword-based, space-separated terms.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5).",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}

_READ_SCHEMA = {
    "name": "memory_wiki_read",
    "description": (
        "Read a compiled memory wiki page by its relative path "
        "(e.g. 'entities/agents/hermes' or 'concepts/handoff-protocol'). "
        "Strips .md suffix if provided. Only compiled pages can be read."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Relative path to the page, without the wiki root prefix. "
                    "E.g. 'entities/agents/hermes' or 'concepts/handoff-protocol'."
                ),
            },
        },
        "required": ["path"],
    },
}

_INGEST_SCHEMA = {
    "name": "memory_wiki_ingest_artifact",
    "description": (
        "Copy an artifact file into the memory wiki's raw/artifacts/ directory and log the ingest. "
        "Returns the destination path. A compiled page update is still required after ingestion."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the artifact file to ingest.",
            },
            "note": {
                "type": "string",
                "description": "Optional note appended to the log entry.",
                "default": "",
            },
        },
        "required": ["path"],
    },
}

_LINT_SCHEMA = {
    "name": "memory_wiki_lint",
    "description": (
        "Run the memory wiki linter. Returns findings as JSON with error/warning counts "
        "and per-page details."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

registry.register(
    name="memory_wiki_search",
    toolset="memory_wiki",
    schema=_SEARCH_SCHEMA,
    handler=lambda args, **kw: memory_wiki_search(
        query=args["query"],
        limit=args.get("limit", 5),
    ),
    emoji="🔍",
)

registry.register(
    name="memory_wiki_read",
    toolset="memory_wiki",
    schema=_READ_SCHEMA,
    handler=lambda args, **kw: memory_wiki_read(path=args["path"]),
    emoji="📖",
)

registry.register(
    name="memory_wiki_ingest_artifact",
    toolset="memory_wiki",
    schema=_INGEST_SCHEMA,
    handler=lambda args, **kw: memory_wiki_ingest_artifact(
        path=args["path"],
        note=args.get("note", ""),
    ),
    emoji="📥",
)

registry.register(
    name="memory_wiki_lint",
    toolset="memory_wiki",
    schema=_LINT_SCHEMA,
    handler=lambda args, **kw: memory_wiki_lint(),
    emoji="🧹",
)
