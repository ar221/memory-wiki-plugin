"""Tests for hermes_cli/memory_wiki.py CLI dispatcher.

Isolation: conftest.py's _hermetic_environment fixture auto-sets HERMES_HOME to
a per-test tempdir, so wiki_root() always resolves inside that tempdir and never
touches the real ~/.hermes.

Tests call memory_wiki_command() directly with argparse.Namespace objects,
bypassing the full CLI parser to keep tests fast and focused.
"""

from __future__ import annotations

import io
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.memory_wiki.paths import wiki_root
from hermes_cli.memory_wiki import memory_wiki_command


# ---------------------------------------------------------------------------
# Shared wiki-building helper (mirrors tests/scripts/test_memory_wiki_lint.py)
# ---------------------------------------------------------------------------

_VALID_FRONTMATTER = """\
---
title: Test Page
created: 2026-04-29
updated: 2026-04-29
type: concept
scope: triad
status: active
tags: [memory, workflow]
sources: []
---
"""

_SCHEMA_CONTENT = """\
# Hermes Memory Wiki Schema

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
"""

_INDEX_TEMPLATE = """\
# Hermes Memory Wiki Index

> Last updated: 2026-04-29 | Total compiled pages: 1

## Concepts

- [[concepts/test-page]] — A test concept page.
"""

_LOG_CONTENT = """\
# Hermes Memory Wiki Log

> Append-only chronological log.

## [2026-04-29] init | test init
"""


def make_wiki() -> Path:
    """Create a minimal valid wiki under wiki_root() and return the root."""
    root = wiki_root()

    for subdir in (
        "entities/agents",
        "entities/people",
        "concepts",
        "decisions",
        "incidents",
        "queries",
        "raw/artifacts",
        "_meta/lint-reports",
        "_meta/promotion-reports",
    ):
        (root / subdir).mkdir(parents=True, exist_ok=True)

    (root / "SCHEMA.md").write_text(_SCHEMA_CONTENT, encoding="utf-8")
    (root / "log.md").write_text(_LOG_CONTENT, encoding="utf-8")

    page = root / "concepts" / "test-page.md"
    page.write_text(
        _VALID_FRONTMATTER + "\n# Test Page\n\nSome content about artifact retention and workflow.\n",
        encoding="utf-8",
    )

    (root / "index.md").write_text(_INDEX_TEMPLATE, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPathPrintsWikiRoot:
    def test_path_prints_wiki_root(self, capsys):
        rc = memory_wiki_command(Namespace(memory_wiki_command="path"))
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out.strip().endswith("memory-wiki")


class TestInitCreatesStructure:
    def test_init_creates_structure(self):
        rc = memory_wiki_command(Namespace(memory_wiki_command="init"))
        assert rc == 0
        root = wiki_root()
        assert (root / "SCHEMA.md").exists(), "SCHEMA.md not created"
        assert (root / "index.md").exists(), "index.md not created"
        assert (root / "log.md").exists(), "log.md not created"


class TestLintCleanWikiExitZero:
    def test_lint_clean_wiki_exit_zero(self, capsys):
        make_wiki()
        rc = memory_wiki_command(Namespace(memory_wiki_command="lint"))
        assert rc == 0


class TestLintDirtyWikiExitOne:
    def test_lint_dirty_wiki_exit_one(self, capsys):
        make_wiki()
        root = wiki_root()
        # Add a page with no frontmatter — will trigger missing_frontmatter error
        bad_page = root / "concepts" / "bad-page.md"
        bad_page.write_text("# No Frontmatter\n\nJust body text.\n", encoding="utf-8")
        # Register it in index.md so missing_from_index doesn't mask the check
        idx = root / "index.md"
        idx.write_text(idx.read_text() + "- [[concepts/bad-page]] — bad page\n")

        rc = memory_wiki_command(Namespace(memory_wiki_command="lint"))
        assert rc == 1


class TestIngestArtifact:
    def test_ingest_artifact(self, tmp_path, capsys):
        make_wiki()
        root = wiki_root()

        tmp_file = tmp_path / "my-artifact.md"
        tmp_file.write_text("# Artifact Content\n\nSome notes.\n", encoding="utf-8")

        rc = memory_wiki_command(
            Namespace(
                memory_wiki_command="ingest-artifact",
                path=str(tmp_file),
                note="test note",
            )
        )
        assert rc == 0

        artifacts_dir = root / "raw" / "artifacts"
        ingested = list(artifacts_dir.glob("*my-artifact*"))
        assert ingested, f"No ingested file found in {artifacts_dir}"

        log_text = (root / "log.md").read_text()
        assert "ingest" in log_text


class TestSearchReturnsResults:
    def test_search_returns_results(self, capsys):
        make_wiki()
        rc = memory_wiki_command(
            Namespace(memory_wiki_command="search", query="artifact", limit=5)
        )
        assert rc == 0
        captured = capsys.readouterr()
        # Should find test-page.md which contains "artifact retention"
        assert captured.out.strip() != ""
        assert "test-page" in captured.out or "artifact" in captured.out.lower()


class TestNoSubcommandShowsUsage:
    def test_no_subcommand_shows_usage(self, capsys):
        rc = memory_wiki_command(Namespace(memory_wiki_command=None))
        assert rc == 1
        captured = capsys.readouterr()
        assert "usage" in captured.out.lower() or "subcommand" in captured.out.lower()
