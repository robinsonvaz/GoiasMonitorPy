from __future__ import annotations

import argparse
from typing import Any

from db import execute, query_all
from tools.fallbacks import extract_article_text, is_relevant_for_goias_entity


def _parse_keywords(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            import json

            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            return []
    return []


def _load_rows(only_id: str | None, limit: int | None) -> list[dict[str, Any]]:
    sql = """
        SELECT
            n.id,
            n.entity_id,
            n.title,
            n.content,
            n.full_content,
            n.full_text,
            n.source_url,
            COALESCE(me.name, '') AS entity_name,
            me.keywords AS entity_keywords
        FROM news_items n
        LEFT JOIN monitored_entities me ON me.id = n.entity_id
        WHERE n.entity_id IS NOT NULL
    """
    params: list[Any] = []
    if only_id:
        sql += " AND n.id = %s"
        params.append(only_id)

    sql += " ORDER BY n.collected_at DESC"
    if limit is not None and limit > 0:
        sql += " LIMIT %s"
        params.append(limit)

    rows = query_all(sql, tuple(params) if params else None)
    return list(rows)


def _build_terms(row: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    entity_name = (row.get("entity_name") or "").strip()
    if entity_name:
        terms.append(entity_name)

    keywords = _parse_keywords(row.get("entity_keywords"))
    terms.extend(keywords)
    return [term for term in terms if term]


def _fetch_full_text_if_needed(row: dict[str, Any], fetch_missing: bool) -> str:
    full_text = (row.get("full_content") or row.get("full_text") or "").strip()
    if full_text or not fetch_missing:
        return full_text

    url = (row.get("source_url") or "").strip()
    if not url:
        return ""

    extracted = extract_article_text(url, summary_mode=False)
    return (extracted or "").strip()


def _save_full_text_if_changed(news_id: str, original: str, updated: str, dry_run: bool) -> bool:
    if not updated or updated == original:
        return False
    if dry_run:
        return True
    execute(
        "UPDATE news_items SET full_content = %s, full_text = COALESCE(full_text, %s) WHERE id = %s",
        (updated, updated, news_id),
    )
    return True


def _detach_news(news_id: str, dry_run: bool) -> None:
    if dry_run:
        return
    execute("UPDATE alerts SET news_item_id = NULL WHERE news_item_id = %s", (news_id,))
    execute("UPDATE news_items SET entity_id = NULL WHERE id = %s", (news_id,))


def _delete_news(news_id: str, dry_run: bool) -> None:
    if dry_run:
        return
    execute("DELETE FROM news_items WHERE id = %s", (news_id,))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Revalida noticias antigas com filtro estrito de contexto de Goias + variacoes da entidade."
        )
    )
    parser.add_argument(
        "--action",
        choices=["report", "detach", "delete"],
        default="report",
        help="Acao para falsos positivos: report (padrao), detach ou delete.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica alteracoes no banco. Sem este flag, executa em dry-run.",
    )
    parser.add_argument(
        "--fetch-missing-full-text",
        action="store_true",
        help="Tenta extrair full_text para registros antigos sem texto completo.",
    )
    parser.add_argument(
        "--news-id",
        default="",
        help="Revalida apenas uma noticia especifica (UUID).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limita a quantidade de noticias analisadas (0 = sem limite).",
    )
    parser.add_argument(
        "--print-false-positives",
        action="store_true",
        help="Exibe detalhes de cada falso positivo identificado.",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    limit = args.limit if args.limit > 0 else None
    only_id = args.news_id.strip() or None

    rows = _load_rows(only_id=only_id, limit=limit)
    if not rows:
        print("Nenhuma noticia encontrada para revalidacao.")
        return

    checked = 0
    relevant = 0
    false_positive = 0
    full_text_enriched = 0
    detached = 0
    deleted = 0

    for row in rows:
        checked += 1
        news_id = str(row["id"])
        title = (row.get("title") or "").strip()
        summary = (row.get("content") or "").strip()
        original_full_text = (row.get("full_content") or row.get("full_text") or "").strip()
        full_text = _fetch_full_text_if_needed(row, fetch_missing=args.fetch_missing_full_text)

        if _save_full_text_if_changed(news_id, original_full_text, full_text, dry_run):
            full_text_enriched += 1

        terms = _build_terms(row)
        is_relevant = is_relevant_for_goias_entity(
            title=title,
            summary=summary,
            full_text=full_text,
            entity_terms=terms,
        )

        if is_relevant:
            relevant += 1
            continue

        false_positive += 1
        if args.print_false_positives:
            print(
                f"[FP] id={news_id} entity='{row.get('entity_name')}' "
                f"url='{(row.get('source_url') or '').strip()}' title='{title[:140]}'"
            )

        if args.action == "detach":
            _detach_news(news_id, dry_run=dry_run)
            detached += 1
        elif args.action == "delete":
            _delete_news(news_id, dry_run=dry_run)
            deleted += 1

    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"Modo: {mode}")
    print(f"Analisadas: {checked}")
    print(f"Relevantes: {relevant}")
    print(f"Falsos positivos: {false_positive}")
    print(f"full_text enriquecido: {full_text_enriched}")
    print(f"Desassociadas: {detached}")
    print(f"Removidas: {deleted}")


if __name__ == "__main__":
    main()
