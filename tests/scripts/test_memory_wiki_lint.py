"""Tests for scripts/memory_wiki/lint.py and ingest_artifact.py.

Isolation: conftest.py's _hermetic_environment fixture auto-sets HERMES_HOME to
a per-test tempdir, so wiki_root() always resolves inside that tempdir and never
touches the real ~/.hermes.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts.memory_wiki.paths import wiki_root
from scripts.memory_wiki import lint as lint_mod
from scripts.memory_wiki import ingest_artifact as ingest_mod


# ---------------------------------------------------------------------------
# Helper: build a minimal valid wiki in the hermetic HERMES_HOME
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

    # Directory structure
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

    # Meta files
    (root / "SCHEMA.md").write_text(_SCHEMA_CONTENT, encoding="utf-8")
    (root / "log.md").write_text(_LOG_CONTENT, encoding="utf-8")

    # One valid compiled page
    page = root / "concepts" / "test-page.md"
    page.write_text(
        _VALID_FRONTMATTER + "\n# Test Page\n\nSome content about memory and workflow.\n",
        encoding="utf-8",
    )

    # index.md lists the page
    (root / "index.md").write_text(_INDEX_TEMPLATE, encoding="utf-8")

    return root


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCleanWikiPasses:
    def test_clean_wiki_passes(self):
        make_wiki()
        findings = lint_mod.run()
        errors = [f for f in findings if f["severity"] == "error"]
        assert errors == [], f"Expected no errors, got: {errors}"


class TestMissingFrontmatter:
    def test_missing_frontmatter(self):
        make_wiki()
        root = wiki_root()
        page = root / "concepts" / "no-fm.md"
        page.write_text("# No Frontmatter\n\nJust body text.\n", encoding="utf-8")
        # Add it to index.md to avoid missing_from_index masking the check
        idx = root / "index.md"
        idx.write_text(idx.read_text() + "- [[concepts/no-fm]] — no frontmatter page\n")

        findings = lint_mod.run()
        matching = [f for f in findings if f["check"] == "missing_frontmatter"]
        assert len(matching) >= 1
        assert any("no-fm.md" in f["path"] for f in matching)


class TestMissingRequiredFields:
    def test_missing_required_fields(self):
        make_wiki()
        root = wiki_root()
        page = root / "concepts" / "no-title.md"
        page.write_text(
            "---\ncreated: 2026-04-29\nupdated: 2026-04-29\ntype: concept\nstatus: active\n---\n\n# Body\n",
            encoding="utf-8",
        )
        idx = root / "index.md"
        idx.write_text(idx.read_text() + "- [[concepts/no-title]] — missing title\n")

        findings = lint_mod.run()
        matching = [
            f for f in findings
            if f["check"] == "missing_required_field" and "no-title.md" in f["path"]
        ]
        assert len(matching) >= 1
        assert any("title" in f["message"] for f in matching)


class TestBrokenWikilink:
    def test_broken_wikilink(self):
        make_wiki()
        root = wiki_root()
        page = root / "concepts" / "broken-link.md"
        page.write_text(
            _VALID_FRONTMATTER
            + "\n# Broken Link\n\nSee [[concepts/nonexistent]] for details.\n",
            encoding="utf-8",
        )
        idx = root / "index.md"
        idx.write_text(idx.read_text() + "- [[concepts/broken-link]] — has broken link\n")

        findings = lint_mod.run()
        matching = [
            f for f in findings
            if f["check"] == "broken_wikilink" and "broken-link.md" in f["path"]
        ]
        assert len(matching) >= 1
        assert any("nonexistent" in f["message"] for f in matching)


class TestMissingFromIndex:
    def test_missing_from_index(self):
        make_wiki()
        root = wiki_root()
        # Add a page but do NOT register it in index.md
        page = root / "concepts" / "unlisted.md"
        page.write_text(
            _VALID_FRONTMATTER + "\n# Unlisted Page\n\nNot in index.\n",
            encoding="utf-8",
        )

        findings = lint_mod.run()
        matching = [
            f for f in findings
            if f["check"] == "missing_from_index" and "unlisted.md" in f["path"]
        ]
        assert len(matching) >= 1


class TestPipedWikilinkInIndex:
    def test_piped_wikilink_in_index_not_flagged(self):
        """A page referenced as [[path|Label]] in index.md must not raise missing_from_index."""
        root = make_wiki()
        # Add a compiled page
        page = root / "concepts" / "my-page.md"
        page.write_text(
            _VALID_FRONTMATTER + "\n# My Page\n\nSome content.\n",
            encoding="utf-8",
        )
        # Register it in index.md using piped wikilink syntax
        idx = root / "index.md"
        idx.write_text(
            idx.read_text() + "- [[concepts/my-page|My Page Label]] — a piped link\n",
            encoding="utf-8",
        )

        findings = lint_mod.run()
        missing = [
            f for f in findings
            if f["check"] == "missing_from_index" and "my-page.md" in f["path"]
        ]
        assert missing == [], (
            f"Piped wikilink should not trigger missing_from_index, got: {missing}"
        )


class TestPageTooLongWarning:
    def test_page_too_long_warning(self):
        make_wiki()
        root = wiki_root()
        page = root / "concepts" / "long-page.md"
        long_body = "\n".join(f"Line {i}" for i in range(210))
        page.write_text(_VALID_FRONTMATTER + "\n" + long_body, encoding="utf-8")
        idx = root / "index.md"
        idx.write_text(idx.read_text() + "- [[concepts/long-page]] — a long page\n")

        findings = lint_mod.run()
        matching = [
            f for f in findings
            if f["check"] == "page_too_long" and "long-page.md" in f["path"]
        ]
        assert len(matching) >= 1
        assert matching[0]["severity"] == "warning"


class TestLintSavesReport:
    def test_lint_saves_report(self):
        make_wiki()
        root = wiki_root()
        today = date.today().isoformat()

        # Manually trigger report write (mimics main())
        findings = lint_mod.run(root)
        lint_mod._write_report(root, findings, today)

        report_path = root / "_meta" / "lint-reports" / f"{today}.md"
        assert report_path.exists(), f"Report not found at {report_path}"
        content = report_path.read_text()
        assert f"Lint Report" in content

    def test_no_overwrite_same_day(self):
        """Second _write_report call on the same day produces a -2 file, not an overwrite."""
        make_wiki()
        root = wiki_root()
        today = date.today().isoformat()

        findings = lint_mod.run(root)
        path1 = lint_mod._write_report(root, findings, today)
        path2 = lint_mod._write_report(root, findings, today)

        assert path1 != path2, "Second report should get a different filename"
        assert path1.exists()
        assert path2.exists()
        assert path2.name == f"{today}-2.md", f"Expected {today}-2.md, got {path2.name}"


class TestIngestArtifact:
    def test_ingest_artifact(self, tmp_path):
        make_wiki()
        root = wiki_root()

        # Create a temp source file to ingest
        src = tmp_path / "my-notes.md"
        src.write_text("# My Notes\n\nSome content.\n", encoding="utf-8")

        dest = ingest_mod.ingest(src, note="test ingest", root=root)

        # Verify destination
        assert dest.exists()
        assert dest.parent == root / "raw" / "artifacts"
        today = date.today().isoformat()
        assert dest.name.startswith(today)
        assert "my-notes" in dest.name

        # Verify log entry
        log_text = (root / "log.md").read_text()
        assert "ingest" in log_text
        assert dest.name in log_text

    def test_ingest_no_overwrite(self, tmp_path):
        """Second ingest of same filename gets a -2 suffix."""
        make_wiki()
        root = wiki_root()

        src = tmp_path / "duplicate.md"
        src.write_text("first", encoding="utf-8")

        dest1 = ingest_mod.ingest(src, root=root)
        dest2 = ingest_mod.ingest(src, root=root)

        assert dest1 != dest2
        assert dest1.exists()
        assert dest2.exists()
        assert "-2" in dest2.name
