"""Simple keyword search over compiled Memory Wiki pages.

Tokenises the query into terms and scores each page by term-frequency hits.
index.md one-liner descriptions receive a 2x bonus weight.

Usage:
    python -m scripts.memory_wiki.search "query terms" [--limit 5]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from scripts.memory_wiki.paths import wiki_root

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COMPILED_DIRS = ("entities", "concepts", "decisions", "incidents", "queries")

# Match [[target]] or [[target|label]] wikilink in index.md for descriptions.
_INDEX_ENTRY_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]\s*[—–-]\s*(.+)")


def _iter_compiled_pages(root: Path):
    for top in _COMPILED_DIRS:
        top_dir = root / top
        if not top_dir.is_dir():
            continue
        for path in sorted(top_dir.rglob("*.md")):
            yield path


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _term_freq(tokens: list[str], term: str) -> int:
    return tokens.count(term)


def _load_index_descriptions(root: Path) -> dict[str, str]:
    """Return {page_rel_no_ext: one-liner description} from index.md."""
    index = root / "index.md"
    if not index.exists():
        return {}
    result: dict[str, str] = {}
    for line in index.read_text(encoding="utf-8").splitlines():
        m = _INDEX_ENTRY_RE.search(line)
        if m:
            target = m.group(1).strip()
            description = m.group(2).strip()
            result[target] = description
    return result


def _get_title_from_frontmatter(text: str) -> str:
    """Extract title from YAML frontmatter, or empty string."""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end == -1:
        return ""
    for line in text[3:end].splitlines():
        if line.startswith("title:"):
            return line[6:].strip()
    return ""


# ---------------------------------------------------------------------------
# Core search function
# ---------------------------------------------------------------------------


def search(query: str, limit: int = 5, root: Path | None = None) -> list[dict]:
    """Return up to *limit* results sorted by score (descending).

    Each result: {path, score, title, description}
    """
    if root is None:
        root = wiki_root()

    terms = _tokenize(query)
    if not terms:
        return []

    descriptions = _load_index_descriptions(root)
    results = []

    for page in _iter_compiled_pages(root):
        text = page.read_text(encoding="utf-8")
        rel_no_ext = str(page.relative_to(root).with_suffix(""))

        title = _get_title_from_frontmatter(text)
        body_tokens = _tokenize(text)
        title_tokens = _tokenize(title)

        score = 0
        for term in terms:
            score += _term_freq(body_tokens, term)
            score += _term_freq(title_tokens, term)  # title already in body but reinforce

        # Bonus: index.md one-liner description (2x weight)
        desc = descriptions.get(rel_no_ext, "")
        if desc:
            desc_tokens = _tokenize(desc)
            for term in terms:
                score += _term_freq(desc_tokens, term) * 2

        if score > 0:
            results.append({
                "path": str(page.relative_to(root)),
                "score": score,
                "title": title or rel_no_ext,
                "description": desc,
            })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Keyword search over compiled Memory Wiki pages."
    )
    parser.add_argument("query", help="Search query string.")
    parser.add_argument("--limit", type=int, default=5, help="Max results to return (default 5).")
    args = parser.parse_args()

    results = search(args.query, limit=args.limit)
    if not results:
        print("No results found.")
        sys.exit(0)

    for r in results:
        if r["description"]:
            suffix = f"{r['title']} | {r['description']}"
        else:
            suffix = r["title"]
        print(f"[{r['score']}] {r['path']} — {suffix}")


if __name__ == "__main__":
    main()
