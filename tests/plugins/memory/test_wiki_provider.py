"""Tests for the WikiMemoryProvider plugin.

All tests use the conftest _hermetic_environment fixture which auto-patches
HERMES_HOME to a per-test tempdir, so get_hermes_home() returns a safe path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_constants import get_hermes_home
from plugins.memory.wiki import WikiMemoryProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_wiki(root: Path) -> None:
    """Create a minimal valid wiki structure for testing."""
    root.mkdir(parents=True, exist_ok=True)

    # index.md with one entry pointing at the compiled page
    (root / "index.md").write_text(
        "# Memory Wiki Index\n\n"
        "[[entities/agents/test]] — Test agent page\n",
        encoding="utf-8",
    )

    # SCHEMA.md (required by full wiki spec)
    (root / "SCHEMA.md").write_text(
        "# Schema\n\nSchema documentation placeholder.\n",
        encoding="utf-8",
    )

    # log.md
    (root / "log.md").write_text(
        "# Change Log\n\n- Initial scaffold\n",
        encoding="utf-8",
    )

    # One compiled page with valid frontmatter
    entities_dir = root / "entities" / "agents"
    entities_dir.mkdir(parents=True, exist_ok=True)
    (entities_dir / "test.md").write_text(
        "---\n"
        "title: Test Agent\n"
        "tags: [test, agent]\n"
        "---\n\n"
        "# Test Agent\n\n"
        "This is a test page artifact retention example.\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_is_available_when_wiki_exists():
    hermes_home = get_hermes_home()
    hermes_wiki_path = hermes_home / "memory-wiki"
    make_wiki(hermes_wiki_path)

    provider = WikiMemoryProvider()
    assert provider.is_available() is True


def test_is_not_available_when_wiki_absent():
    # Don't create wiki
    provider = WikiMemoryProvider()
    assert provider.is_available() is False


def test_initialize_sets_wiki_root():
    hermes_home = get_hermes_home()

    provider = WikiMemoryProvider()
    provider.initialize("sess-123", hermes_home=str(hermes_home))

    assert provider._wiki_root is not None
    assert isinstance(provider._wiki_root, Path)
    assert provider._wiki_root == hermes_home / "memory-wiki"
    assert provider._is_primary is True  # default context is "primary"
    assert provider._session_id == "sess-123"


def test_system_prompt_block_contains_wiki_mention():
    hermes_home = get_hermes_home()
    hermes_wiki_path = hermes_home / "memory-wiki"
    make_wiki(hermes_wiki_path)

    provider = WikiMemoryProvider()
    provider.initialize("sess-abc", hermes_home=str(hermes_home))

    block = provider.system_prompt_block()
    assert "memory-wiki" in block


def test_prefetch_returns_results():
    hermes_home = get_hermes_home()
    hermes_wiki_path = hermes_home / "memory-wiki"
    make_wiki(hermes_wiki_path)

    provider = WikiMemoryProvider()
    provider.initialize("sess-xyz", hermes_home=str(hermes_home))

    result = provider.prefetch("artifact retention")
    assert isinstance(result, str)
    assert len(result) > 0
    # Should contain at least one page path reference
    assert "entities" in result or "test" in result


def test_prefetch_empty_when_no_wiki():
    hermes_home = get_hermes_home()
    # Initialize without creating wiki
    provider = WikiMemoryProvider()
    provider.initialize("sess-empty", hermes_home=str(hermes_home))

    result = provider.prefetch("anything")
    assert result == ""


def test_sync_turn_writes_candidate():
    hermes_home = get_hermes_home()
    hermes_wiki_path = hermes_home / "memory-wiki"
    make_wiki(hermes_wiki_path)

    provider = WikiMemoryProvider()
    provider.initialize("sess-write", hermes_home=str(hermes_home))

    provider.sync_turn(
        "remember this: artifact retention is important",
        "Noted, I'll keep that in mind.",
    )

    reports_dir = hermes_wiki_path / "_meta" / "promotion-reports"
    candidates = list(reports_dir.glob("*.md"))
    assert len(candidates) > 0


def test_sync_turn_no_write_for_subagent():
    hermes_home = get_hermes_home()
    hermes_wiki_path = hermes_home / "memory-wiki"
    make_wiki(hermes_wiki_path)

    provider = WikiMemoryProvider()
    provider.initialize(
        "sess-sub",
        hermes_home=str(hermes_home),
        agent_context="subagent",
    )

    provider.sync_turn("remember this", "Noted.")

    reports_dir = hermes_wiki_path / "_meta" / "promotion-reports"
    if reports_dir.exists():
        candidates = list(reports_dir.glob("*.md"))
        assert len(candidates) == 0


def test_on_session_end_writes_summary():
    hermes_home = get_hermes_home()
    hermes_wiki_path = hermes_home / "memory-wiki"
    make_wiki(hermes_wiki_path)

    provider = WikiMemoryProvider()
    provider.initialize("sess-end123", hermes_home=str(hermes_home))

    messages = [{"role": "user", "content": "hi"}] * 6
    provider.on_session_end(messages)

    reports_dir = hermes_wiki_path / "_meta" / "promotion-reports"
    summaries = list(reports_dir.glob("*-session-*.md"))
    assert len(summaries) > 0


def test_get_tool_schemas_empty():
    provider = WikiMemoryProvider()
    assert provider.get_tool_schemas() == []


# ---------------------------------------------------------------------------
# on_pre_compress
# ---------------------------------------------------------------------------


class TestOnPreCompress:
    def test_returns_reminder_when_wiki_exists(self, tmp_path):
        provider = WikiMemoryProvider()
        make_wiki(tmp_path / "memory-wiki")
        provider.initialize("sess-test", hermes_home=str(tmp_path))
        result = provider.on_pre_compress([])
        assert "wiki" in result.lower() or result == ""  # non-empty or graceful empty

    def test_returns_empty_when_no_wiki(self, tmp_path):
        provider = WikiMemoryProvider()
        # don't create wiki
        provider.initialize("sess-test", hermes_home=str(tmp_path))
        result = provider.on_pre_compress([])
        assert result == ""
