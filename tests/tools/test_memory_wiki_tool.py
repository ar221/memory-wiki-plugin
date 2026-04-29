"""Tests for tools/memory_wiki_tool.py.

Isolation: conftest.py's _hermetic_environment fixture auto-sets HERMES_HOME to
a per-test tempdir, so wiki_root() / get_hermes_home() always resolve to the
tempdir and never touch the real ~/.hermes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.memory_wiki.paths import wiki_root
from tools.memory_wiki_tool import (
    memory_wiki_ingest_artifact,
    memory_wiki_lint,
    memory_wiki_read,
    memory_wiki_search,
)


# ---------------------------------------------------------------------------
# Shared wiki-building helpers (mirrors tests/hermes_cli/test_memory_wiki_cli.py)
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


def make_wiki(tmp_path: Path | None = None) -> Path:
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
        _VALID_FRONTMATTER
        + "\n# Test Page\n\nSome content about artifact retention and workflow.\n",
        encoding="utf-8",
    )

    (root / "index.md").write_text(_INDEX_TEMPLATE, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# memory_wiki_search tests
# ---------------------------------------------------------------------------


class TestMemoryWikiSearch:
    def test_search_returns_results(self):
        """Create a wiki with searchable text; confirm results list is non-empty."""
        make_wiki()
        result = json.loads(memory_wiki_search("artifact", 5))
        assert "results" in result, f"Expected 'results' key, got: {result}"
        assert len(result["results"]) > 0, "Expected at least one search result"

    def test_search_no_wiki(self):
        """No wiki created; search should return an error JSON."""
        result = json.loads(memory_wiki_search("anything"))
        assert "error" in result, f"Expected 'error' key when wiki absent, got: {result}"


# ---------------------------------------------------------------------------
# memory_wiki_read tests
# ---------------------------------------------------------------------------


class TestMemoryWikiRead:
    def test_read_existing_page(self):
        """Create a page; reading it should return JSON with 'content' key."""
        root = make_wiki()
        # Ensure the page exists at entities/agents/test.md
        page = root / "entities" / "agents" / "test.md"
        page.write_text(
            _VALID_FRONTMATTER.replace("type: concept", "type: entity")
            + "\n# Test Agent\n\nThis is a test entity page.\n",
            encoding="utf-8",
        )
        # Also add it to index.md so lint would pass (not strictly required here)
        idx = root / "index.md"
        idx.write_text(idx.read_text() + "- [[entities/agents/test]] — test agent\n")

        result = json.loads(memory_wiki_read("entities/agents/test"))
        assert "content" in result, f"Expected 'content' key, got: {result}"
        assert "test entity page" in result["content"]

    def test_read_nonexistent_page(self):
        """Reading a page that doesn't exist should return an error JSON."""
        make_wiki()
        result = json.loads(memory_wiki_read("entities/agents/ghost"))
        assert "error" in result, f"Expected 'error' key for missing page, got: {result}"

    def test_read_path_traversal_rejected(self):
        """Path traversal attempts should be blocked."""
        make_wiki()
        result = json.loads(memory_wiki_read("../../etc/passwd"))
        assert "error" in result, f"Expected 'error' key for traversal, got: {result}"

    def test_read_no_wiki(self):
        """Reading a page when the wiki is absent should return an error JSON."""
        # Deliberately do NOT call make_wiki() — wiki directory must not exist.
        result = json.loads(memory_wiki_read("concepts/anything"))
        assert "error" in result, f"Expected 'error' key when wiki absent, got: {result}"


# ---------------------------------------------------------------------------
# memory_wiki_ingest_artifact tests
# ---------------------------------------------------------------------------


class TestMemoryWikiIngestArtifact:
    @pytest.fixture
    def allowed_src_dir(self, tmp_path, monkeypatch):
        """Monkeypatch _INGEST_ALLOWED_ROOTS to a temp dir so no real ~/. paths are touched."""
        src_root = tmp_path / "allowed_sources"
        src_root.mkdir()
        monkeypatch.setattr(
            "tools.memory_wiki_tool._INGEST_ALLOWED_ROOTS",
            (src_root,)
        )
        return src_root

    def test_ingest_artifact(self, allowed_src_dir):
        """Ingest a normal artifact file from a monkeypatched allowed root; assert success."""
        make_wiki()
        root = wiki_root()

        artifact_file = allowed_src_dir / "my-artifact.md"
        artifact_file.write_text("# Artifact\n\nSome notes.\n", encoding="utf-8")

        result = json.loads(memory_wiki_ingest_artifact(str(artifact_file)))
        assert result.get("success") is True, f"Expected success=True, got: {result}"

        artifacts_dir = root / "raw" / "artifacts"
        ingested = list(artifacts_dir.glob("*my-artifact*"))
        assert ingested, f"No ingested file found in {artifacts_dir}"

    def test_ingest_secret_rejected(self, allowed_src_dir):
        """Ingesting a file named auth.json should be refused (name heuristic)."""
        make_wiki()
        auth_file = allowed_src_dir / "auth.json"
        auth_file.write_text('{"token": "secret-value"}', encoding="utf-8")

        result = json.loads(memory_wiki_ingest_artifact(str(auth_file)))
        assert "error" in result, f"Expected 'error' key for secret file, got: {result}"

    def test_ingest_credential_content_rejected(self, allowed_src_dir):
        """Ingesting a benign-named file with credential content should be refused."""
        make_wiki()
        notes_file = allowed_src_dir / "notes.md"
        notes_file.write_text(
            "# Notes\n\npassword: supersecret123\n", encoding="utf-8"
        )

        result = json.loads(memory_wiki_ingest_artifact(str(notes_file)))
        assert "error" in result, (
            f"Expected 'error' key when file contains credential pattern, got: {result}"
        )

    def test_ingest_disallowed_root_rejected(self, tmp_path, monkeypatch):
        """Ingesting a file from outside the monkeypatched allowlist should be refused."""
        make_wiki()
        # Monkeypatch allowed roots to a dedicated subdir; tmp_path itself is outside it.
        allowed_root = tmp_path / "allowed_sources"
        allowed_root.mkdir()
        monkeypatch.setattr(
            "tools.memory_wiki_tool._INGEST_ALLOWED_ROOTS",
            (allowed_root,)
        )

        outside_file = tmp_path / "outside.md"
        outside_file.write_text("# Artifact\n\nSome notes.\n", encoding="utf-8")

        result = json.loads(memory_wiki_ingest_artifact(str(outside_file)))
        assert "error" in result, f"Expected 'error' for disallowed root, got: {result}"
        assert "allowed directory" in result["error"].lower(), (
            f"Expected 'allowed directory' in error message, got: {result}"
        )


# ---------------------------------------------------------------------------
# memory_wiki_lint tests
# ---------------------------------------------------------------------------


class TestMemoryWikiLint:
    def test_lint_clean(self):
        """A valid wiki should produce errors == 0 with warnings and findings keys present."""
        make_wiki()
        result = json.loads(memory_wiki_lint())
        assert "errors" in result, f"Expected 'errors' key, got: {result}"
        assert result["errors"] == 0, f"Expected 0 errors, got: {result}"
        assert "warnings" in result, f"Expected 'warnings' key, got: {result}"
        assert "findings" in result, f"Expected 'findings' key, got: {result}"
        assert isinstance(result["findings"], list), (
            f"Expected 'findings' to be a list, got: {type(result['findings'])}"
        )

    def test_lint_no_wiki(self):
        """Linting without a wiki should return an error JSON."""
        result = json.loads(memory_wiki_lint())
        assert "error" in result, f"Expected 'error' key when wiki absent, got: {result}"
