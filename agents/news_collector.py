"""Web news collection agent (local MySQL storage)."""
from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import urlparse

from config import FIRECRAWL_API_KEY, SCRAPINGBEE_API_KEY
from db import query_all, execute
from tools import firecrawl, scrapingbee, ai_classifier


def run(entity_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
    if not FIRECRAWL_API_KEY and not SCRAPINGBEE_API_KEY:
        return {"success": False, "error": "Nenhum crawler configurado (Firecrawl ou ScrapingBee)"}

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
    firecrawl_exhausted = False
    used_fallback = False

    for entity in entities:
        search_terms = " OR ".join([entity["name"]] + (entity.get("keywords") or []))
        search_query = f"{search_terms} Goiás notícia"

        results = []

        if FIRECRAWL_API_KEY and not firecrawl_exhausted:
            try:
                hits, exhausted = firecrawl.search(FIRECRAWL_API_KEY, search_query, limit=5)
                if exhausted:
                    firecrawl_exhausted = True
                else:
                    results = hits
            except Exception as exc:
                print(f"[Firecrawl] Error for {entity['name']}: {exc}")

        if not results and SCRAPINGBEE_API_KEY:
            try:
                results = scrapingbee.search(SCRAPINGBEE_API_KEY, search_query, limit=5)
                used_fallback = True
            except Exception as exc:
                print(f"[ScrapingBee] Error for {entity['name']}: {exc}")
                continue

        if not results:
            continue

        urls = [r.url for r in results if r.url]
        existing_urls = set()
        if urls:
            placeholders = ",".join(["%s"] * len(urls))
            existing_rows = query_all(
                f"SELECT source_url FROM news_items WHERE source_url IN ({placeholders})",
                tuple(urls),
            )
            existing_urls = {row["source_url"] for row in existing_rows}

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

    msg = None
    if firecrawl_exhausted:
        if used_fallback:
            msg = "Créditos Firecrawl esgotados. ScrapingBee utilizado como alternativa."
        else:
            msg = "Créditos Firecrawl esgotados e ScrapingBee indisponível."

    return {
        "success": True,
        "collected": total_collected,
        "fallback_used": used_fallback,
        "firecrawl_exhausted": firecrawl_exhausted,
        "message": msg,
    }
