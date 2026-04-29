"""Memory wiki subcommand dispatcher for the Hermes CLI.

Delegates to the scripts/memory_wiki/ package functions without going through
their argparse entrypoints.
"""

from __future__ import annotations

import sys
from pathlib import Path


def memory_wiki_command(args) -> int:
    """Dispatch memory-wiki subcommands.

    Returns an integer exit code (0 = success, 1 = failure / errors found).
    Does NOT call sys.exit — that is the caller's responsibility so that unit
    tests can assert on the return value cleanly.
    """
    sub = getattr(args, "memory_wiki_command", None)

    if sub is None:
        print("usage: hermes memory-wiki <subcommand>")
        print("subcommands: init, ingest-artifact, search, lint, path, promote")
        return 1

    if sub == "path":
        return _cmd_path()

    if sub == "init":
        return _cmd_init()

    if sub == "lint":
        return _cmd_lint()

    if sub == "ingest-artifact":
        return _cmd_ingest(args)

    if sub == "search":
        return _cmd_search(args)

    if sub == "promote":
        return _cmd_promote(args)

    print(f"error: unknown memory-wiki subcommand: {sub!r}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def _cmd_path() -> int:
    from scripts.memory_wiki.paths import wiki_root

    print(str(wiki_root()))
    return 0


def _cmd_init() -> int:
    from scripts.memory_wiki.init import init
    from scripts.memory_wiki.paths import wiki_root

    root = wiki_root()
    init(root)
    print(f"Memory wiki ready at: {root}")
    return 0


def _cmd_lint() -> int:
    from scripts.memory_wiki import lint as lint_mod
    from scripts.memory_wiki.paths import wiki_root

    findings = lint_mod.run(root=wiki_root())
    errors = [f for f in findings if f.get("severity") == "error"]
    return 1 if errors else 0


def _cmd_ingest(args) -> int:
    from scripts.memory_wiki.ingest_artifact import ingest
    from scripts.memory_wiki.paths import wiki_root

    src = Path(args.path)
    if not src.exists():
        print(f"error: file not found: {src}", file=sys.stderr)
        return 1
    if not src.is_file():
        print(f"error: not a file: {src}", file=sys.stderr)
        return 1

    note = getattr(args, "note", None) or None
    root = wiki_root()
    dest = ingest(src, note=note, root=root)
    print(f"Ingested: {dest}")
    print("Compiled page update still required.")
    return 0


def _cmd_search(args) -> int:
    from scripts.memory_wiki.search import search
    from scripts.memory_wiki.paths import wiki_root

    root = wiki_root()
    limit = getattr(args, "limit", 5)
    results = search(args.query, limit=limit, root=root)

    if not results:
        print("No results found.")
        return 0

    for r in results:
        desc = r.get("description")
        if desc:
            suffix = f"{r.get('title')} | {desc}"
        else:
            suffix = r.get("title")
        print(f"[{r.get('score')}] {r.get('path')} — {suffix}")

    return 0


def _cmd_promote(args) -> int:
    from datetime import date

    from scripts.memory_wiki.paths import wiki_root
    from scripts.memory_wiki.promote import (
        apply_proposals,
        classify_candidates,
        load_candidates,
        parse_since,
        propose_updates,
        write_promotion_report,
    )

    since_str = getattr(args, "since", "24h")
    auto_approve = getattr(args, "auto_approve", False)

    try:
        cutoff = parse_since(since_str)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    root = wiki_root()
    candidates = load_candidates(root, cutoff)

    if not candidates:
        print("No promotion candidates found.")
        return 0

    groups = classify_candidates(candidates)
    proposals = propose_updates(groups, root)

    # Print summary
    total_touches = len(proposals)
    print(f"Found {len(candidates)} candidate(s) across {len(groups)} topic(s):")
    for p in proposals:
        action_label = f"update {p['suggested_page']}" if p["action"] == "update" else f"create {p['new_page_path']}"
        print(f"  [{p['topic']}] {len(p['candidates'])} candidate(s) → {action_label}")

    # approval gate: > 3 topic groups triggers confirmation
    if total_touches > 3 and not auto_approve:
        try:
            answer = input(f"\nThis will touch {total_touches} pages. Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer != "y":
            today = date.today().isoformat()
            report_dir = root / "_meta" / "promotion-reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            draft_path = report_dir / f"{today}-promote-draft.md"
            try:
                lines = [f"# Promotion Draft (not applied) — {today}\n\n"]
                lines.append(f"**Candidates**: {len(candidates)}\n\n")
                for p in proposals:
                    lines.append(f"- [{p['topic']}] {p['action']} → {p.get('suggested_page') or p['new_page_path']}\n")
                draft_path.write_text("".join(lines), encoding="utf-8")
                print(f"\nDraft saved (not applied): {draft_path}")
            except OSError as exc:
                print(f"warning: could not save draft: {exc}", file=sys.stderr)
            return 0

    touched = apply_proposals(proposals, root)
    today = date.today().isoformat()
    write_promotion_report(touched, root, today)

    if touched:
        print(f"\nApplied {len(touched)} page update(s):")
        for path in touched:
            print(f"  {path}")
    else:
        print("\nNo pages were written (all proposals failed — check stderr).")

    return 0
