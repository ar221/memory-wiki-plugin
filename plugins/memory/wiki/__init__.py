"""Wiki MemoryProvider plugin — compiled memory wiki integration.

Provides prefetch-based recall from synthesised markdown pages stored at
``<HERMES_HOME>/memory-wiki/``.  The wiki is a compiled corpus of facts,
decisions, and entity profiles synthesised from prior sessions.

Lifecycle roles:
  - ``system_prompt_block`` — static notice to prefer the wiki over raw recall
  - ``prefetch``            — top-3 keyword-matched pages surfaced before each turn
  - ``sync_turn``           — heuristic promotion-candidate detection
  - ``on_session_end``      — session summary candidate if ≥5 messages (primary only)
  - ``on_pre_compress``     — reminder not to compress away decisions/preferences

Tools are NOT re-exposed here.  The ``memory_wiki`` toolset registers all four
tools (search, read, lint, ingest_artifact) independently; this provider's job
is passive enrichment and candidate filing.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from agent.memory_provider import MemoryProvider

logger = logging.getLogger(__name__)


class WikiMemoryProvider(MemoryProvider):
    """MemoryProvider backed by the compiled Hermes Memory Wiki."""

    def __init__(self) -> None:
        self._wiki_root: Path | None = None
        self._is_primary: bool = True
        self._session_id: str = ""

    # ── Identity ────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "wiki"

    # ── Availability ────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Return True if the wiki index exists at the canonical HERMES_HOME path."""
        try:
            from hermes_constants import get_hermes_home
            return (get_hermes_home() / "memory-wiki" / "index.md").exists()
        except Exception:
            return False

    # ── Initialization ──────────────────────────────────────────────────────

    def initialize(self, session_id: str, **kwargs) -> None:
        """Resolve wiki root and session context from kwargs."""
        from hermes_constants import get_hermes_home

        hermes_home = kwargs.get("hermes_home")
        if hermes_home:
            self._wiki_root = Path(hermes_home) / "memory-wiki"
        else:
            self._wiki_root = get_hermes_home() / "memory-wiki"

        self._is_primary = kwargs.get("agent_context", "primary") == "primary"
        self._session_id = str(session_id or "")
        logger.debug(
            "WikiMemoryProvider initialized: root=%s, primary=%s, session=%s",
            self._wiki_root, self._is_primary, self._session_id,
        )

    # ── System prompt ────────────────────────────────────────────────────────

    def system_prompt_block(self) -> str:
        """Return a static notice about the compiled wiki when it exists."""
        if not self._wiki_root:
            return ""
        if not (self._wiki_root / "index.md").exists():
            return ""
        return (
            "A compiled memory wiki is available at ~/.hermes/memory-wiki/. "
            "Prefer compiled wiki pages over raw transcript recall for facts about "
            "Hermes, Oracle, Alfred, preferences, workflows, and decisions. "
            "Use the memory_wiki_search, memory_wiki_read, memory_wiki_lint, and "
            "memory_wiki_ingest_artifact tools to interact with it."
        )

    # ── Prefetch ─────────────────────────────────────────────────────────────

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Keyword-search the wiki and return a brief context block (top 3 hits)."""
        if not self._wiki_root or not self._wiki_root.is_dir():
            return ""
        if not (self._wiki_root / "index.md").exists():
            return ""
        try:
            from scripts.memory_wiki.search import search  # deferred — path safety
            results = search(query, limit=3, root=self._wiki_root)
            if not results:
                return ""
            lines = ["## Memory Wiki — Relevant Pages"]
            for r in results:
                lines.append(f"- [[{r['path']}]] — {r.get('title', r['path'])}")
            return "\n".join(lines)
        except Exception:
            logger.debug("WikiMemoryProvider.prefetch failed", exc_info=True)
            return ""

    # ── Sync turn (promotion heuristics) ─────────────────────────────────────

    _HEURISTIC_PHRASES = (
        "remember this",
        "don't do that",
        "we decided",
        "implementation plan",
    )
    _DURABLE_PREF_RE = re.compile(
        r'\b(always|never)\s+(use|run|do|make|keep|set|call|write|push|commit|skip|avoid|prefer)\b',
        re.IGNORECASE,
    )

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
    ) -> None:
        """Write a promotion candidate file if a heuristic signal fires."""
        if not self._is_primary:
            return
        if not self._wiki_root:
            return

        lower_user = user_content.lower()
        lower_asst = assistant_content.lower()
        combined = lower_user + " " + lower_asst

        trigger: str | None = None

        for phrase in self._HEURISTIC_PHRASES:
            if phrase in combined:
                trigger = phrase
                break

        if trigger is None:
            if self._DURABLE_PREF_RE.search(combined):
                trigger = "durable preference"

        if trigger is None:
            return

        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            ts = datetime.now(timezone.utc).strftime("%H%M%S%f")
            sid_slug = (session_id or self._session_id or "unknown")[:8]
            filename = f"{date_str}-candidate-{sid_slug}-{ts}.md"

            reports_dir = self._wiki_root / "_meta" / "promotion-reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            user_excerpt = user_content[:500]
            asst_excerpt = assistant_content[:500]

            content = (
                f"# Promotion Candidate\n\n"
                f"date: {date_str}\n"
                f"session_id: {session_id or self._session_id}\n"
                f"trigger: {trigger}\n\n"
                f"## User Turn Excerpt\n\n{user_excerpt}\n\n"
                f"## Assistant Turn Excerpt\n\n{asst_excerpt}\n"
            )
            (reports_dir / filename).write_text(content, encoding="utf-8")
            logger.debug("WikiMemoryProvider: wrote candidate %s", filename)
        except Exception:
            logger.debug("WikiMemoryProvider.sync_turn write failed", exc_info=True)

    # ── Session end ──────────────────────────────────────────────────────────

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Write a session summary candidate if primary and ≥5 messages."""
        if not self._is_primary:
            return
        if not self._wiki_root:
            return
        if len(messages) < 5:
            return

        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            sid_short = self._session_id[:8] if self._session_id else "unknown"
            filename = f"{date_str}-session-{sid_short}.md"

            reports_dir = self._wiki_root / "_meta" / "promotion-reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            user_msgs = [m for m in messages if m.get("role") == "user"]
            first_user = (user_msgs[0].get("content") or "")[:300] if user_msgs else ""
            last_user = (user_msgs[-1].get("content") or "")[:300] if user_msgs else ""

            content = (
                f"# Session Summary Candidate\n\n"
                f"date: {date_str}\n"
                f"session_id: {self._session_id}\n"
                f"message_count: {len(messages)}\n\n"
                f"## First User Message\n\n{first_user}\n\n"
                f"## Last User Message\n\n{last_user}\n"
            )
            (reports_dir / filename).write_text(content, encoding="utf-8")
            logger.debug("WikiMemoryProvider: wrote session summary %s", filename)
        except Exception:
            logger.debug("WikiMemoryProvider.on_session_end write failed", exc_info=True)

    # ── Pre-compress reminder ────────────────────────────────────────────────

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        """Remind the compressor not to lose decisions or preferences."""
        if not self._wiki_root or not (self._wiki_root / "index.md").exists():
            return ""
        return (
            "Memory wiki available — check wiki before compressing preferences or decisions."
        )

    # ── Tool schemas ─────────────────────────────────────────────────────────

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return empty list — tools are registered via the memory_wiki toolset."""
        return []

    # ── Shutdown ─────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """No-op — no connections to close."""


def register(ctx) -> None:
    """Register the WikiMemoryProvider plugin."""
    ctx.register_memory_provider(WikiMemoryProvider())
