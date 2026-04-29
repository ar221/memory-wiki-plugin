"""Linter for the Hermes Memory Wiki.

Checks all compiled pages (under entities/, concepts/, decisions/, incidents/,
queries/) for common issues and produces a JSON findings list plus a markdown
report saved to _meta/lint-reports/YYYY-MM-DD.md.

Usage:
    python -m scripts.memory_wiki.lint

Exit code:
    0  — no errors (warnings may be present)
    1  — one or more errors found
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

from scripts.memory_wiki.paths import wiki_root

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Top-level directories that hold compiled pages.
_COMPILED_DIRS = ("entities", "concepts", "decisions", "operations", "projects", "incidents", "queries", "qa")

# Frontmatter fields every compiled page must declare.
_REQUIRED_FIELDS = ("title", "created", "updated", "type", "status")

# Pattern to find wikilinks: [[some/path]] or [[some/path|label]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")

# Pattern to extract the target (left side) from index.md wikilink entries,
# handling both [[target]] and [[target|label]] forms.
_WIKILINK_TARGET_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

# Patterns to strip code blocks and inline code before wikilink scanning.
# Fenced code blocks (``` ... ```) and inline backtick spans (`...`).
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_compiled_pages(root: Path):
    """Yield all .md files under the compiled-page directories."""
    for top in _COMPILED_DIRS:
        top_dir = root / top
        if not top_dir.is_dir():
            continue
        for path in sorted(top_dir.rglob("*.md")):
            yield path


def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Return a dict of frontmatter key→value, or None if no frontmatter block."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fm_block = text[3:end].strip()
    result: dict[str, Any] = {}
    lines = fm_block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if ":" not in line:
            i += 1
            continue
        key, _, raw_val = line.partition(":")
        key = key.strip()
        raw_val = raw_val.strip()
        # Tags / sources are often YAML inline lists: [a, b, c]
        if raw_val.startswith("[") and raw_val.endswith("]"):
            inner = raw_val[1:-1]
            result[key] = [t.strip() for t in inner.split(",") if t.strip()]
        elif raw_val == "":
            # Bare key: collect following `  - item` continuation lines (block list).
            items: list[str] = []
            i += 1
            while i < len(lines):
                m = re.match(r"^\s+-\s+(.+)", lines[i])
                if m:
                    items.append(m.group(1).strip())
                    i += 1
                else:
                    break
            result[key] = items if items else ""
            continue  # i already advanced past the list items
        else:
            result[key] = raw_val
        i += 1
    return result


def _load_allowed_tags(schema_path: Path) -> set[str]:
    """Parse the ## Tags section of SCHEMA.md and return the allowed tag set."""
    try:
        text = schema_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return set()

    tags: set[str] = set()
    in_tags = False
    for line in text.splitlines():
        if re.match(r"^## Tags", line):
            in_tags = True
            continue
        if in_tags:
            if line.startswith("## "):
                break  # next section
            m = re.match(r"^- (\S+)", line)
            if m:
                tags.add(m.group(1))
    return tags


def _load_index_text(root: Path) -> str:
    index = root / "index.md"
    try:
        return index.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


# ---------------------------------------------------------------------------
# Core lint function
# ---------------------------------------------------------------------------


def run(root: Path | None = None) -> list[dict[str, str]]:
    """Run all lint checks and return a list of finding dicts.

    Each finding: {path, check, severity, message}
    """
    if root is None:
        root = wiki_root()

    findings: list[dict[str, str]] = []
    allowed_tags = _load_allowed_tags(root / "SCHEMA.md")
    index_text = _load_index_text(root)

    for page in _iter_compiled_pages(root):
        rel = page.relative_to(root)
        rel_str = str(rel)
        text = page.read_text(encoding="utf-8")
        lines = text.splitlines()

        # --- 1. Missing frontmatter ---
        fm = _parse_frontmatter(text)
        if fm is None:
            findings.append({
                "path": rel_str,
                "check": "missing_frontmatter",
                "severity": "error",
                "message": f"{rel_str}: page does not start with YAML frontmatter block",
            })
            # Without frontmatter many checks below can't run — skip them.
            continue

        # --- 2. Missing required fields ---
        for field in _REQUIRED_FIELDS:
            if field not in fm or not fm[field]:
                findings.append({
                    "path": rel_str,
                    "check": "missing_required_field",
                    "severity": "error",
                    "message": f"{rel_str}: missing required frontmatter field '{field}'",
                })

        # --- 3. Broken wikilinks ---
        # Strip fenced code blocks and inline code before scanning so that
        # wikilink syntax used as documentation examples (e.g. `[[wikilinks]]`)
        # doesn't generate false-positive broken-wikilink errors.
        scannable_text = _FENCED_CODE_RE.sub("", text)
        scannable_text = _INLINE_CODE_RE.sub("", scannable_text)
        for m in _WIKILINK_RE.finditer(scannable_text):
            target = m.group(1).strip()
            target_path = root / f"{target}.md"
            if not target_path.exists():
                findings.append({
                    "path": rel_str,
                    "check": "broken_wikilink",
                    "severity": "error",
                    "message": f"{rel_str}: wikilink [[{target}]] has no matching file",
                })

        # --- 4. Missing from index.md ---
        # index.md uses [[entities/agents/hermes]] or [[entities/agents/hermes|Label]]
        # form (no .md suffix).  Build a set of all wikilink targets from index_text
        # so that piped wikilinks like [[path|Friendly Label]] are also recognised.
        rel_no_ext = str(rel.with_suffix(""))
        indexed_targets = set(_WIKILINK_TARGET_RE.findall(index_text))
        if rel_no_ext not in indexed_targets:
            findings.append({
                "path": rel_str,
                "check": "missing_from_index",
                "severity": "error",
                "message": f"{rel_str}: page not listed in index.md",
            })

        # --- 5. Page too long ---
        if len(lines) > 200:
            findings.append({
                "path": rel_str,
                "check": "page_too_long",
                "severity": "warning",
                "message": f"{rel_str}: page has {len(lines)} lines (limit 200)",
            })

        # --- 6. Unknown tags ---
        if allowed_tags:  # skip check if SCHEMA.md is absent / has no Tags section
            page_tags = fm.get("tags", [])
            if isinstance(page_tags, list):
                for tag in page_tags:
                    if tag and tag not in allowed_tags:
                        findings.append({
                            "path": rel_str,
                            "check": "unknown_tag",
                            "severity": "warning",
                            "message": f"{rel_str}: tag '{tag}' not listed in SCHEMA.md",
                        })

    return findings


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _write_report(root: Path, findings: list[dict[str, str]], today: str) -> Path:
    """Write markdown report to _meta/lint-reports/<date>.md and return the path.

    If YYYY-MM-DD.md already exists (same-day re-run), tries YYYY-MM-DD-2.md,
    YYYY-MM-DD-3.md, etc. until a free slot is found — never silently overwrites.
    """
    report_dir = root / "_meta" / "lint-reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    candidate = report_dir / f"{today}.md"
    if candidate.exists():
        suffix_num = 2
        while True:
            candidate = report_dir / f"{today}-{suffix_num}.md"
            if not candidate.exists():
                break
            suffix_num += 1
    report_path = candidate

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]

    lines = [
        f"# Lint Report — {today}",
        "",
        f"**Errors:** {len(errors)}  **Warnings:** {len(warnings)}",
        "",
    ]

    if errors:
        lines += ["## Errors", ""]
        for f in errors:
            lines.append(f"- `{f['path']}` [{f['check']}]: {f['message']}")
        lines.append("")

    if warnings:
        lines += ["## Warnings", ""]
        for f in warnings:
            lines.append(f"- `{f['path']}` [{f['check']}]: {f['message']}")
        lines.append("")

    if not errors and not warnings:
        lines += ["No issues found.", ""]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _append_log(root: Path, today: str, errors: int, warnings: int) -> None:
    log_path = root / "log.md"
    entry = f"\n## [{today}] lint | {errors} errors, {warnings} warnings\n"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        pass  # Don't fail the lint run if logging fails.


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main() -> None:
    root = wiki_root()
    today = date.today().isoformat()

    findings = run(root)
    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]

    # JSON to stdout
    print(json.dumps(findings, indent=2))

    # Markdown report + log entry
    report_path = _write_report(root, findings, today)
    _append_log(root, today, len(errors), len(warnings))

    print(f"\nReport saved: {report_path}", file=sys.stderr)
    print(
        f"Summary: {len(errors)} error(s), {len(warnings)} warning(s)",
        file=sys.stderr,
    )

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
