"""Quick cleanup: remove HTML tags from titles already saved in database.

This script is useful for fixing titles that were captured with HTML markup (e.g., <b>, <strong>).
Default mode is DRY-RUN. Use --apply to persist updates.
"""
from __future__ import annotations

import argparse
from html import unescape
import re
from typing import Any

from db import execute_many, query_all


_TAG_RE = re.compile(r"<[^>]+>")


def _sanitize_title(value: str) -> str:
    """Remove HTML tags and decode entities from title."""
    cleaned = unescape(value or "")
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _load_candidates(limit: int | None) -> list[dict[str, Any]]:
    """Load news items with HTML tags in title."""
    # Fetch all rows without LIKE pattern issues - check in Python instead
    sql = "SELECT id, title FROM news_items"
    params: list[Any] = []

    if limit is not None and limit > 0:
        sql += " LIMIT %s"
        params.append(limit)

    rows = query_all(sql, tuple(params) if params else None) or []
    
    # Filter in Python to find titles with HTML tags
    candidates = [
        row for row in rows
        if row.get("title") and ("<" in row["title"] and ">" in row["title"])
    ]
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove HTML tags from titles already saved in database."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates to database. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of records to process (0 = no limit).",
    )
    parser.add_argument(
        "--print-samples",
        action="store_true",
        help="Print sample before/after titles for inspection.",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    limit = args.limit if args.limit > 0 else None

    rows = _load_candidates(limit=limit)
    if not rows:
        print("No titles with HTML tags found in database.")
        return

    checked = 0
    updated_count = 0
    updates: list[tuple[str, str]] = []

    for row in rows:
        checked += 1
        news_id = str(row["id"])
        original_title = row.get("title") or ""
        sanitized_title = _sanitize_title(original_title)

        if original_title == sanitized_title:
            continue

        updated_count += 1
        updates.append((sanitized_title, news_id))

        if args.print_samples:
            print(f"[CLEANUP] id={news_id}")
            print(f"  Before: {original_title[:220]}")
            print(f"  After:  {sanitized_title[:220]}")

    if updates and not dry_run:
        execute_many(
            """
            UPDATE news_items
            SET title = %s
            WHERE id = %s
            """,
            updates,
        )

    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"\nMode: {mode}")
    print(f"Checked: {checked}")
    print(f"Candidates for cleanup: {updated_count}")
    print(f"Updated in database: {len(updates) if not dry_run else 0}")


if __name__ == "__main__":
    main()
