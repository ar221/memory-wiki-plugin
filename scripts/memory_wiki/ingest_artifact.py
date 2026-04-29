"""Ingest an artifact file into the Hermes Memory Wiki raw/artifacts/ directory.

Copies the file into raw/artifacts/ with a date prefix, appends to log.md,
and prints a reminder that a compiled page update is still required.

Usage:
    python -m scripts.memory_wiki.ingest_artifact /path/to/file.md [--note "optional note"]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

from scripts.memory_wiki.paths import wiki_root


def _dest_path(artifacts_dir: Path, basename: str, today: str) -> Path:
    """Return a non-colliding destination path under artifacts_dir."""
    stem_ext = basename
    candidate = artifacts_dir / f"{today}-{stem_ext}"
    if not candidate.exists():
        return candidate
    # Add numeric suffix to avoid overwrite: YYYY-MM-DD-name-2.md, -3, etc.
    suffix_num = 2
    name_part = Path(stem_ext).stem
    ext_part = Path(stem_ext).suffix
    while True:
        candidate = artifacts_dir / f"{today}-{name_part}-{suffix_num}{ext_part}"
        if not candidate.exists():
            return candidate
        suffix_num += 1


def ingest(src: Path, note: str | None = None, root: Path | None = None) -> Path:
    """Copy *src* into raw/artifacts/ and append to log.md.

    Returns the destination path.
    """
    if root is None:
        root = wiki_root()

    artifacts_dir = root / "raw" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    dest = _dest_path(artifacts_dir, src.name, today)
    shutil.copy2(src, dest)

    # Append to log.md
    log_path = root / "log.md"
    note_suffix = f" — {note}" if note else ""
    entry = f"\n## [{today}] ingest | artifact: {dest.name}{note_suffix}\n"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        pass  # Don't fail the ingest if log is unavailable.

    return dest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest an artifact file into the Memory Wiki raw/artifacts/ directory."
    )
    parser.add_argument("file", help="Path to the artifact file to ingest.")
    parser.add_argument("--note", default=None, help="Optional note appended to the log entry.")
    args = parser.parse_args()

    src = Path(args.file)
    if not src.exists():
        print(f"Error: file not found: {src}", file=sys.stderr)
        sys.exit(1)
    if not src.is_file():
        print(f"Error: not a file: {src}", file=sys.stderr)
        sys.exit(1)

    dest = ingest(src, note=args.note)
    print(f"Ingested: {dest}")
    print("Compiled page update still required.")


if __name__ == "__main__":
    main()
