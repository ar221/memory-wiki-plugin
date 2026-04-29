"""Promote candidates from _meta/promotion-reports/ into compiled wiki pages.

No LLM calls.  Pure text manipulation.  All file writes are guarded with
try/except so a single failure never aborts the whole promotion run.

Usage (module-level functions are gate-free; the 10-page gate lives in the CLI):
    from scripts.memory_wiki.promote import (
        parse_since, load_candidates, classify_candidates,
        propose_updates, apply_proposals, write_promotion_report,
    )
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Topic → directory mapping
# ---------------------------------------------------------------------------

_TOPIC_DIRS: dict[str, str] = {
    "preference": "concepts/preferences",
    "workflow":   "concepts/workflows",
    "decision":   "decisions",
    "incident":   "incidents",
    "project":    "entities/projects",
}

# Type field used in frontmatter per topic
_TOPIC_TYPES: dict[str, str] = {
    "preference": "concept",
    "workflow":   "concept",
    "decision":   "decision",
    "incident":   "incident",
    "project":    "entity",
}

# Score threshold: if top search result is in the topic dir AND score >= this,
# propose an update rather than creating a new page.
_SEARCH_UPDATE_THRESHOLD = 3

# ---------------------------------------------------------------------------
# 1. parse_since
# ---------------------------------------------------------------------------

def parse_since(since: str) -> datetime:
    """Parse a --since argument and return the cutoff datetime (UTC).

    Supports:
        Nh  — N hours ago         e.g. "24h"
        Nd  — N days ago          e.g. "7d"
        today — midnight UTC today
    """
    since = since.strip().lower()
    if since == "today":
        d = date.today()
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)

    m = re.fullmatch(r"(\d+)h", since)
    if m:
        return datetime.now(tz=timezone.utc) - timedelta(hours=int(m.group(1)))

    m = re.fullmatch(r"(\d+)d", since)
    if m:
        return datetime.now(tz=timezone.utc) - timedelta(days=int(m.group(1)))

    raise ValueError(
        f"Invalid --since value: {since!r}. Expected e.g. '24h', '7d', or 'today'."
    )


# ---------------------------------------------------------------------------
# 2. load_candidates
# ---------------------------------------------------------------------------

def _parse_candidate_file(path: Path) -> Optional[dict]:
    """Parse a single candidate file.  Return None if Date: is missing."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    data: dict = {"path": str(path), "raw": text}

    for line in text.splitlines():
        if line.startswith("Date:"):
            data["date_str"] = line[5:].strip()
        elif line.startswith("Session:"):
            data["session"] = line[8:].strip()
        elif line.startswith("Trigger:"):
            data["trigger"] = line[8:].strip()
        elif line.startswith("User:"):
            data["user"] = line[5:].strip()
        elif line.startswith("Assistant:"):
            data["assistant"] = line[10:].strip()

    if "date_str" not in data:
        return None

    try:
        data["date"] = date.fromisoformat(data["date_str"])
    except ValueError:
        return None

    return data


def load_candidates(root: Path, since: datetime) -> list[dict]:
    """Read candidate files from <root>/_meta/promotion-reports/, return those
    whose Date: is on or after *since* (inclusive at the date boundary).

    Files whose names end with ``-promotion.md`` are output reports, not
    candidates — they are skipped.
    """
    reports_dir = root / "_meta" / "promotion-reports"
    if not reports_dir.is_dir():
        return []

    cutoff_date = since.date() if hasattr(since, "date") else since

    candidates = []
    for p in sorted(reports_dir.glob("*.md")):
        # Skip output promotion reports (written by write_promotion_report)
        if p.name.endswith("-promotion.md"):
            continue
        parsed = _parse_candidate_file(p)
        if parsed is None:
            continue
        if parsed["date"] >= cutoff_date:
            candidates.append(parsed)

    return candidates


# ---------------------------------------------------------------------------
# 3. classify_candidates
# ---------------------------------------------------------------------------

def _classify_one(candidate: dict) -> str:
    """Return the topic string for a single candidate dict."""
    text = " ".join([
        candidate.get("trigger", ""),
        candidate.get("user", ""),
        candidate.get("assistant", ""),
    ]).lower()

    if "decided" in text or "decision" in text:
        return "decision"
    if "broke" in text or "bug" in text or "error" in text:
        return "incident"
    if "workflow" in text or "process" in text or "how to" in text:
        return "workflow"
    if "project" in text or "campaign" in text or "task" in text:
        return "project"
    return "preference"


def classify_candidates(candidates: list[dict]) -> dict[str, list]:
    """Group candidates by topic.

    Returns: {topic: [candidate, ...]}
    """
    groups: dict[str, list] = {}
    for c in candidates:
        topic = _classify_one(c)
        groups.setdefault(topic, []).append(c)
    return groups


# ---------------------------------------------------------------------------
# 4. propose_updates
# ---------------------------------------------------------------------------

def _build_append_content(candidates: list[dict], today: str) -> str:
    """Build the markdown section to append to an existing page."""
    lines = [f"\n## Promoted {today}\n"]
    for c in candidates:
        session = c.get("session", "unknown")
        trigger = c.get("trigger", "")
        user = c.get("user", "")
        assistant = c.get("assistant", "")
        lines.append(f"- **Session**: {session}")
        if trigger:
            lines.append(f"  **Trigger**: {trigger}")
        if user:
            lines.append(f"  **User**: {user}")
        if assistant:
            lines.append(f"  **Assistant**: {assistant}")
        lines.append("")
    return "\n".join(lines)


def _build_new_page_content(topic: str, candidates: list[dict], today: str) -> str:
    """Build the full markdown for a newly created page."""
    type_field = _TOPIC_TYPES.get(topic, "concept")
    title = f"Promoted {topic.title()} — {today}"
    fm = (
        f"---\n"
        f"title: {title}\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"type: {type_field}\n"
        f"scope: triad\n"
        f"status: stub\n"
        f"tags: [promotion, {topic}]\n"
        f"sources: []\n"
        f"---\n"
    )

    body_lines = [f"\n# {title}\n\n*Auto-promoted from session candidates.*\n"]
    for c in candidates:
        session = c.get("session", "unknown")
        trigger = c.get("trigger", "")
        user = c.get("user", "")
        assistant = c.get("assistant", "")
        body_lines.append(f"## Session {session}\n")
        if trigger:
            body_lines.append(f"**Trigger**: {trigger}\n")
        if user:
            body_lines.append(f"**User**: {user}\n")
        if assistant:
            body_lines.append(f"**Assistant**: {assistant}\n")

    return fm + "\n".join(body_lines)


def propose_updates(groups: dict, root: Path) -> list[dict]:
    """For each group, return a proposal dict.

    Each proposal:
    {
        topic:           str,
        candidates:      list[dict],
        suggested_page:  str | None,   # path relative to root; None if new
        action:          "update" | "create",
        content_to_add:  str,          # content to append (update) or full file (create)
        new_page_path:   str,          # relative path under root (always set)
    }
    """
    from datetime import date as _date
    today = _date.today().isoformat()

    try:
        from scripts.memory_wiki.search import search as wiki_search
    except ImportError:
        wiki_search = None

    proposals = []
    for topic, candidates in groups.items():
        topic_dir = _TOPIC_DIRS.get(topic, "concepts/preferences")
        slug = f"{today}-from-candidates"
        new_rel = f"{topic_dir}/{slug}.md"

        # Try to find a top-matching existing page to update
        action = "create"
        suggested_page: Optional[str] = None

        if wiki_search is not None:
            # Build a query from the first candidate
            c0 = candidates[0]
            query = " ".join([
                c0.get("trigger", ""),
                c0.get("user", ""),
                topic,
            ])[:200]
            try:
                results = wiki_search(query, limit=3, root=root)
            except Exception:
                results = []

            for r in results:
                if r["score"] >= _SEARCH_UPDATE_THRESHOLD and r["path"].startswith(topic_dir):
                    action = "update"
                    suggested_page = r["path"]
                    break

        if action == "update" and suggested_page:
            content_to_add = _build_append_content(candidates, today)
        else:
            content_to_add = _build_new_page_content(topic, candidates, today)

        proposals.append({
            "topic": topic,
            "candidates": candidates,
            "suggested_page": suggested_page,
            "action": action,
            "content_to_add": content_to_add,
            "new_page_path": new_rel,
        })

    return proposals


# ---------------------------------------------------------------------------
# 5. apply_proposals
# ---------------------------------------------------------------------------

def _append_log(log_path: Path, entry: str) -> None:
    """Append a line to log.md, creating it if missing."""
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as exc:
        print(f"[promote] warning: could not write to {log_path}: {exc}", file=sys.stderr)


def _append_index(index_path: Path, rel_path: str, topic: str, today: str) -> None:
    """Add a wikilink entry for a new page to index.md."""
    try:
        rel_no_ext = rel_path[:-3] if rel_path.endswith(".md") else rel_path
        entry = f"- [[{rel_no_ext}]] — Promoted {topic} candidates {today}\n"
        new_file = not index_path.exists()
        with open(index_path, "a", encoding="utf-8") as f:
            if new_file:
                f.write("# Hermes Memory Wiki Index\n\n")
            f.write(entry)
    except OSError as exc:
        print(f"[promote] warning: could not update {index_path}: {exc}", file=sys.stderr)


def apply_proposals(proposals: list[dict], root: Path) -> list[str]:
    """Write changes for each proposal.  Return list of actually-touched paths
    (relative to root).  Failures are logged to stderr; they do NOT raise.
    """
    from datetime import date as _date
    today = _date.today().isoformat()

    log_path = root / "log.md"
    index_path = root / "index.md"
    touched: list[str] = []

    for proposal in proposals:
        topic = proposal["topic"]
        action = proposal["action"]

        if action == "update":
            page_rel = proposal["suggested_page"]
            page_abs = root / page_rel
            try:
                existing = page_abs.read_text(encoding="utf-8")
                page_abs.write_text(
                    existing + proposal["content_to_add"],
                    encoding="utf-8",
                )
                touched.append(page_rel)
                _append_log(
                    log_path,
                    f"\n## [{today}] promote | updated {page_rel} ({len(proposal['candidates'])} candidates)\n",
                )
            except OSError as exc:
                print(
                    f"[promote] error: could not update {page_abs}: {exc}",
                    file=sys.stderr,
                )

        else:  # "create"
            new_rel = proposal["new_page_path"]
            new_abs = root / new_rel
            try:
                new_abs.parent.mkdir(parents=True, exist_ok=True)
                # Avoid overwriting if already exists (rare collision, same-day double run)
                if new_abs.exists():
                    stem = new_abs.stem
                    suffix = new_abs.suffix
                    counter = 2
                    while new_abs.exists():
                        new_abs = new_abs.parent / f"{stem}-{counter}{suffix}"
                        counter += 1
                    new_rel = str(new_abs.relative_to(root))

                new_abs.write_text(proposal["content_to_add"], encoding="utf-8")
                touched.append(new_rel)
                _append_index(index_path, new_rel, topic, today)
                _append_log(
                    log_path,
                    f"\n## [{today}] promote | created {new_rel} ({len(proposal['candidates'])} candidates)\n",
                )
            except OSError as exc:
                print(
                    f"[promote] error: could not create {new_abs}: {exc}",
                    file=sys.stderr,
                )

    return touched


# ---------------------------------------------------------------------------
# 6. write_promotion_report
# ---------------------------------------------------------------------------

def write_promotion_report(touched: list[str], root: Path, date_str: str) -> None:
    """Write a promotion report to _meta/promotion-reports/YYYY-MM-DD-promotion.md."""
    reports_dir = root / "_meta" / "promotion-reports"
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / f"{date_str}-promotion.md"

        # Avoid overwriting same-day report
        if report_path.exists():
            counter = 2
            while report_path.exists():
                report_path = reports_dir / f"{date_str}-promotion-{counter}.md"
                counter += 1

        lines = [
            f"# Promotion Report — {date_str}\n\n",
            f"**Pages touched**: {len(touched)}\n\n",
        ]
        if touched:
            lines.append("## Pages\n\n")
            for p in touched:
                lines.append(f"- {p}\n")
        else:
            lines.append("No pages were written.\n")

        report_path.write_text("".join(lines), encoding="utf-8")
    except OSError as exc:
        print(
            f"[promote] warning: could not write promotion report: {exc}",
            file=sys.stderr,
        )
