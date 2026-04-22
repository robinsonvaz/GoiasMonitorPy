"""Web news collection agent (local MySQL storage)."""
from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import urlparse

from db import query_all, execute
from tools import ai_classifier, google_search


def _existing_url_set(urls: list[str]) -> set[str]:
    if not urls:
        return set()
    placeholders = ",".join(["%s"] * len(urls))
    existing_rows = query_all(
        f"SELECT source_url FROM news_items WHERE source_url IN ({placeholders})",
        tuple(urls),
    )
    return {row["source_url"] for row in existing_rows}


def run(entity_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
    if entity_id:
        entities = query_all(
            "SELECT * FROM monitored_entities WHERE is_active = 1 AND id = %s",
            (entity_id,),
        )
    else:
        entities = query_all(
            "SELECT * FROM monitored_entities WHERE is_active = 1"
        )

    for e in entities:
        e["keywords"] = json.loads(e["keywords"]) if isinstance(e.get("keywords"), str) and e.get("keywords") else []

    if not entities:
        return {"success": True, "collected": 0, "message": "Nenhuma entidade ativa"}

    total_collected = 0
    strategy_counts = {"google_news": 0, "open_web": 0}

    for entity in entities:
        search_terms = " OR ".join([entity["name"]] + (entity.get("keywords") or []))
        search_query = f"{search_terms} Goiás notícia"

        results: list[google_search.SearchResult] = []
        seen_urls: set[str] = set()

        # Strategy 1: prioritize Google News results.
        try:
            news_results = google_search.search_google_news(search_query, limit=5)
            for item in news_results:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                results.append(item)
            strategy_counts["google_news"] += len(news_results)
        except Exception as exc:
            print(f"[GoogleNews] Error for {entity['name']}: {exc}")

        # Strategy 2 (fallback/expansion): if few *new* candidates remain.
        current_urls = [r.url for r in results if r.url]
        existing_after_news = _existing_url_set(current_urls)
        unseen_after_news = [r for r in results if r.url not in existing_after_news]
        if len(unseen_after_news) < 3:
            try:
                web_results = google_search.search_open_web(search_query, limit=7)
                for item in web_results:
                    if item.url in seen_urls:
                        continue
                    seen_urls.add(item.url)
                    results.append(item)
                strategy_counts["open_web"] += len(web_results)
            except Exception as exc:
                print(f"[OpenWeb] Error for {entity['name']}: {exc}")

        if not results:
            continue

        urls = [r.url for r in results if r.url]
        existing_urls = _existing_url_set(urls)

        new_results = [r for r in results if r.url not in existing_urls]
        if not new_results:
            continue

        for result in new_results:
            text_content = result.markdown or result.description or result.title
            classified = ai_classifier.classify_news(text_content, result.title, result.url, entity["name"])

            if not classified or not classified.get("relevant"):
                continue

            try:
                source_name = (urlparse(result.url).hostname or "").replace("www.", "")
            except Exception:
                source_name = ""

            execute(
                """
                INSERT INTO news_items
                (id, entity_id, title, content, source_url, source_name, classification, sentiment,
                 people_mentioned, published_at, collected_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NOW(6), NOW(6))
                """,
                (
                    str(uuid.uuid4()),
                    entity["id"],
                    classified.get("title") or result.title,
                    classified.get("content") or result.description or None,
                    result.url,
                    source_name,
                    classified.get("classification", "outro"),
                    classified.get("sentiment", "neutro"),
                    json.dumps(classified.get("people_mentioned") or [], ensure_ascii=False),
                ),
            )
            total_collected += 1

            negative = (
                classified.get("sentiment") == "negativo"
                or classified.get("classification") == "midia_negativa"
            )
            if negative and user_id:
                execute(
                    """
                    INSERT INTO alerts
                    (id, user_id, news_item_id, title, message, alert_type, is_read, created_at)
                    VALUES (%s, %s, NULL, %s, %s, %s, 0, NOW(6))
                    """,
                    (
                        str(uuid.uuid4()),
                        user_id,
                        f"Mídia negativa: {entity['name']}",
                        classified.get("title") or result.title,
                        "warning",
                    ),
                )

    msg = (
        "Busca concluída com 2 estratégias: "
        f"Google News ({strategy_counts['google_news']} resultados) e "
        f"Internet aberta ({strategy_counts['open_web']} resultados)."
    )

    return {
        "success": True,
        "collected": total_collected,
        "google_news_results": strategy_counts["google_news"],
        "open_web_results": strategy_counts["open_web"],
        "message": msg,
    }
