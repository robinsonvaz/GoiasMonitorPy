"""Cleanup duplicated news records based on normalized URL, title and content."""
from __future__ import annotations

import argparse
from collections import Counter

from db import ensure_local_schema, execute_many, query_all
from tools.news_dedup import build_dedup_fields


def _chunked(seq: list[str], size: int) -> list[list[str]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def _find_duplicates() -> tuple[list[str], Counter[str]]:
    rows = query_all(
        """
        SELECT id, title, content, full_content, full_text, source_url, collected_at, created_at
        FROM news_items
        ORDER BY collected_at ASC, created_at ASC, id ASC
        """
    )

    seen_by_url: dict[str, str] = {}
    seen_by_key: dict[str, str] = {}
    seen_by_title_content: dict[tuple[str, str], str] = {}

    duplicate_ids: list[str] = []
    reasons: Counter[str] = Counter()

    for row in rows:
        dedup = build_dedup_fields(
            title=row.get("title"),
            content=row.get("content"),
            full_text=row.get("full_content") or row.get("full_text"),
            source_url=row.get("source_url"),
        )

        duplicate_reason: str | None = None
        source_url_norm = dedup["source_url_norm"]
        dedup_key = dedup["dedup_key"]
        pair = (dedup["title_norm"], dedup["content_hash"])

        if source_url_norm and source_url_norm in seen_by_url:
            duplicate_reason = "url"
        elif dedup_key and dedup_key in seen_by_key:
            duplicate_reason = "title+content"
        elif pair[0] and pair[1] and pair in seen_by_title_content:
            duplicate_reason = "title+content"

        if duplicate_reason:
            duplicate_ids.append(row["id"])
            reasons[duplicate_reason] += 1
            continue

        if source_url_norm:
            seen_by_url[source_url_norm] = row["id"]
        if dedup_key:
            seen_by_key[dedup_key] = row["id"]
        if pair[0] and pair[1]:
            seen_by_title_content[pair] = row["id"]

    return duplicate_ids, reasons


def _backfill_dedup_fields() -> int:
    rows = query_all(
        """
        SELECT id, title, content, full_content, full_text, source_url
        FROM news_items
        """
    )
    params: list[tuple[str | None, str | None, str | None, str | None, str | None, str]] = []
    for row in rows:
        dedup = build_dedup_fields(
            title=row.get("title"),
            content=row.get("content"),
            full_text=row.get("full_content") or row.get("full_text"),
            source_url=row.get("source_url"),
        )
        params.append(
            (
                dedup["source_url_norm"] or None,
                dedup["title_norm"] or None,
                dedup["content_hash"] or None,
                dedup["dedup_key"] or None,
                (row.get("full_content") or row.get("full_text") or row.get("content") or None),
                row["id"],
            )
        )

    if not params:
        return 0

    return execute_many(
        """
        UPDATE news_items
        SET source_url_norm = %s,
            title_norm = %s,
            content_hash = %s,
            dedup_key = %s,
            full_content = COALESCE(full_content, %s)
        WHERE id = %s
        """,
        params,
    )


def _delete_duplicates(ids: list[str]) -> int:
    total_deleted = 0
    for chunk in _chunked(ids, 500):
        params = [(news_id,) for news_id in chunk]
        total_deleted += execute_many("DELETE FROM news_items WHERE id = %s", params)
    return total_deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="Limpa noticias duplicadas em news_items")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica delecao. Sem essa flag, executa apenas dry-run.",
    )
    args = parser.parse_args()

    ensure_local_schema()
    updated_rows = _backfill_dedup_fields()
    duplicate_ids, reasons = _find_duplicates()

    print(f"Registros normalizados: {updated_rows}")
    print(f"Duplicadas encontradas: {len(duplicate_ids)}")
    print(f"- Por URL: {reasons.get('url', 0)}")
    print(f"- Por titulo+conteudo: {reasons.get('title+content', 0)}")

    if not args.apply:
        print("Modo: DRY-RUN (nenhuma linha removida)")
        return

    deleted = _delete_duplicates(duplicate_ids)
    print("Modo: APPLY")
    print(f"Removidas: {deleted}")


if __name__ == "__main__":
    main()
