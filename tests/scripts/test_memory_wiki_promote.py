"""Tests for scripts/memory_wiki/promote.py.

Isolation: conftest.py's _hermetic_environment fixture auto-sets HERMES_HOME
to a per-test tempdir, so wiki_root() never touches the real ~/.hermes.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.memory_wiki.paths import wiki_root
from scripts.memory_wiki.promote import (
    apply_proposals,
    classify_candidates,
    load_candidates,
    parse_since,
    propose_updates,
    write_promotion_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate_file(reports_dir: Path, filename: str, date_str: str, **kwargs) -> Path:
    """Write a minimal candidate file and return its path."""
    lines = [f"Date: {date_str}"]
    if "session" in kwargs:
        lines.append(f"Session: {kwargs['session']}")
    if "trigger" in kwargs:
        lines.append(f"Trigger: {kwargs['trigger']}")
    if "user" in kwargs:
        lines.append(f"User: {kwargs['user']}")
    if "assistant" in kwargs:
        lines.append(f"Assistant: {kwargs['assistant']}")
    p = reports_dir / filename
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _make_wiki(root: Path) -> None:
    """Create a minimal wiki structure under *root*."""
    for subdir in (
        "concepts/preferences",
        "concepts/workflows",
        "decisions",
        "incidents",
        "entities/projects",
        "_meta/promotion-reports",
        "raw/artifacts",
    ):
        (root / subdir).mkdir(parents=True, exist_ok=True)

    (root / "index.md").write_text("# Hermes Memory Wiki Index\n\n", encoding="utf-8")
    (root / "log.md").write_text(
        "# Hermes Memory Wiki Log\n\n> Append-only chronological log.\n\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# 1. parse_since — hours
# ---------------------------------------------------------------------------

class TestParseSinceHours:
    def test_parse_since_hours(self):
        cutoff = parse_since("24h")
        now = datetime.now(tz=timezone.utc)
        delta = now - cutoff
        # Should be within ~1 second of 24 hours
        assert timedelta(hours=23, minutes=59) < delta < timedelta(hours=24, minutes=1)


# ---------------------------------------------------------------------------
# 2. parse_since — days
# ---------------------------------------------------------------------------

class TestParseSinceDays:
    def test_parse_since_days(self):
        cutoff = parse_since("7d")
        now = datetime.now(tz=timezone.utc)
        delta = now - cutoff
        assert timedelta(days=6, hours=23) < delta < timedelta(days=7, hours=1)


# ---------------------------------------------------------------------------
# 3. parse_since — today
# ---------------------------------------------------------------------------

class TestParseSinceToday:
    def test_parse_since_today(self):
        cutoff = parse_since("today")
        today_midnight = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
        assert cutoff == today_midnight


# ---------------------------------------------------------------------------
# 4. load_candidates — date filter
# ---------------------------------------------------------------------------

class TestLoadCandidatesFiltersByDate:
    def test_filters_by_date(self):
        root = wiki_root()
        _make_wiki(root)
        reports_dir = root / "_meta" / "promotion-reports"

        today_str = date.today().isoformat()
        old_str = (date.today() - timedelta(days=5)).isoformat()

        _make_candidate_file(reports_dir, "recent-1.md", today_str, session="s1", user="hello")
        _make_candidate_file(reports_dir, "recent-2.md", today_str, session="s2", user="world")
        _make_candidate_file(reports_dir, "old-1.md", old_str, session="s3", user="stale")

        # cutoff: 24h ago — today's files should pass, 5-day-old file should not
        cutoff = parse_since("24h")
        candidates = load_candidates(root, cutoff)

        assert len(candidates) == 2
        sessions = {c["session"] for c in candidates}
        assert sessions == {"s1", "s2"}


# ---------------------------------------------------------------------------
# 5. classify — decision keyword
# ---------------------------------------------------------------------------

class TestClassifyDecision:
    def test_classify_decision(self):
        candidates = [{"trigger": "", "user": "we decided to use fish shell", "assistant": "", "raw": ""}]
        groups = classify_candidates(candidates)
        assert "decision" in groups
        assert len(groups["decision"]) == 1


# ---------------------------------------------------------------------------
# 6. classify — workflow keyword
# ---------------------------------------------------------------------------

class TestClassifyWorkflow:
    def test_classify_workflow(self):
        candidates = [{"trigger": "workflow", "user": "describe the workflow", "assistant": "", "raw": ""}]
        groups = classify_candidates(candidates)
        assert "workflow" in groups


# ---------------------------------------------------------------------------
# 7. classify — default preference
# ---------------------------------------------------------------------------

class TestClassifyPreferenceDefault:
    def test_classify_preference_default(self):
        candidates = [{"trigger": "", "user": "I like dark themes", "assistant": "Noted.", "raw": ""}]
        groups = classify_candidates(candidates)
        assert "preference" in groups


# ---------------------------------------------------------------------------
# 8. apply_proposals — create action
# ---------------------------------------------------------------------------

class TestApplyCreatesNewPage:
    def test_apply_creates_new_page(self):
        root = wiki_root()
        _make_wiki(root)

        today = date.today().isoformat()
        proposal = {
            "topic": "preference",
            "candidates": [
                {"session": "s-new", "trigger": "remember", "user": "I prefer short summaries", "assistant": "OK."}
            ],
            "suggested_page": None,
            "action": "create",
            "content_to_add": (
                "---\ntitle: Test\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
                "type: concept\nscope: triad\nstatus: stub\ntags: []\nsources: []\n---\n\n# Test\n"
            ),
            "new_page_path": f"concepts/preferences/{today}-from-candidates.md",
        }

        touched = apply_proposals([proposal], root)

        # Verify file exists on disk
        expected = root / f"concepts/preferences/{today}-from-candidates.md"
        assert expected.exists(), f"Expected page not created: {expected}"
        assert len(touched) == 1
        assert touched[0] == f"concepts/preferences/{today}-from-candidates.md"

        # Verify index.md updated
        index_text = (root / "index.md").read_text()
        assert "from-candidates" in index_text

        # Verify log.md appended
        log_text = (root / "log.md").read_text()
        assert "promote" in log_text


# ---------------------------------------------------------------------------
# 9. apply_proposals — update action
# ---------------------------------------------------------------------------

class TestApplyUpdatesExistingPage:
    def test_apply_updates_existing_page(self):
        root = wiki_root()
        _make_wiki(root)

        # Create an existing page to update
        existing_page = root / "concepts" / "preferences" / "existing.md"
        existing_page.write_text(
            "---\ntitle: Existing\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
            "type: concept\nscope: triad\nstatus: active\ntags: []\nsources: []\n---\n\n# Existing\n\nOriginal content.\n",
            encoding="utf-8",
        )

        today = date.today().isoformat()
        append_content = f"\n## Promoted {today}\n\n- Session: s-update\n  User: I use vim keybindings\n"

        proposal = {
            "topic": "preference",
            "candidates": [
                {"session": "s-update", "trigger": "", "user": "I use vim keybindings", "assistant": "Got it."}
            ],
            "suggested_page": "concepts/preferences/existing.md",
            "action": "update",
            "content_to_add": append_content,
            "new_page_path": f"concepts/preferences/{today}-from-candidates.md",
        }

        touched = apply_proposals([proposal], root)

        # Check file was updated
        updated_text = existing_page.read_text()
        assert "Promoted" in updated_text
        assert "s-update" in updated_text
        assert len(touched) == 1
        assert touched[0] == "concepts/preferences/existing.md"


# ---------------------------------------------------------------------------
# 10. load_candidates — empty dir
# ---------------------------------------------------------------------------

class TestNoCandidatesReturnsEarly:
    def test_no_candidates_returns_early(self):
        root = wiki_root()
        _make_wiki(root)

        cutoff = parse_since("24h")
        candidates = load_candidates(root, cutoff)

        assert candidates == []


# ---------------------------------------------------------------------------
# 11. load_candidates — skips promotion output files
# ---------------------------------------------------------------------------

class TestLoadCandidatesSkipsPromotionOutputFiles:
    def test_load_candidates_skips_promotion_output_files(self):
        root = wiki_root()
        _make_wiki(root)
        reports_dir = root / "_meta" / "promotion-reports"

        today_str = date.today().isoformat()

        # An output promotion report — must be skipped
        output_file = reports_dir / f"{today_str}-promotion.md"
        output_file.write_text(
            f"Date: {today_str}\nSession: output\nTrigger: irrelevant\n",
            encoding="utf-8",
        )

        # A real candidate file — must be returned
        _make_candidate_file(reports_dir, "real-candidate.md", today_str, session="s-real", user="I prefer tabs")

        cutoff = parse_since("24h")
        candidates = load_candidates(root, cutoff)

        assert len(candidates) == 1
        assert candidates[0]["session"] == "s-real"


# ---------------------------------------------------------------------------
# 12. propose_updates — action and required keys
# ---------------------------------------------------------------------------

class TestProposeUpdateAction:
    def test_propose_update_action(self):
        root = wiki_root()
        _make_wiki(root)

        groups = {
            "preference": [
                {
                    "session": "s-test",
                    "trigger": "remember this",
                    "user": "I prefer light backgrounds",
                    "assistant": "Got it.",
                    "raw": "Date: 2026-04-29\nSession: s-test\n",
                    "date_str": "2026-04-29",
                    "date": date(2026, 4, 29),
                    "path": str(root / "_meta" / "promotion-reports" / "test.md"),
                }
            ]
        }

        proposals = propose_updates(groups, root)

        assert len(proposals) == 1
        p = proposals[0]
        assert "action" in p
        assert p["action"] in ("create", "update")
        assert "suggested_page" in p
        assert "content_to_add" in p
        assert isinstance(p["content_to_add"], str)
        assert len(p["content_to_add"]) > 0


# ---------------------------------------------------------------------------
# 13. write_promotion_report — collision avoidance
# ---------------------------------------------------------------------------

class TestWritePromotionReportNoOverwrite:
    def test_write_promotion_report_no_overwrite(self):
        root = wiki_root()
        _make_wiki(root)

        date_str = "2026-04-29"
        touched = ["concepts/preferences/2026-04-29-from-candidates.md"]

        write_promotion_report(touched, root, date_str)
        write_promotion_report(touched, root, date_str)

        reports_dir = root / "_meta" / "promotion-reports"
        report_files = list(reports_dir.glob(f"{date_str}-promotion*.md"))
        assert len(report_files) == 2, (
            f"Expected 2 distinct report files, got {len(report_files)}: {report_files}"
        )
