"""Social media news collection agent (local MySQL storage)."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any
from urllib.parse import urlparse

import requests

from config import LOVABLE_API_KEY
from db import query_all, execute
from tools import google_search, ai_classifier

SOCIAL_PLATFORMS = [
    {"prefix": "site:x.com", "label": "X/Twitter"},
    {"prefix": "site:instagram.com", "label": "Instagram"},
    {"prefix": "site:facebook.com", "label": "Facebook"},
]


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
    if not LOVABLE_API_KEY:
        return {"success": False, "error": "LOVABLE_API_KEY não configurada"}

    if entity_id:
        entities = query_all(
            "SELECT * FROM monitored_entities WHERE is_active = 1 AND id = %s",
            (entity_id,),
        )
    else:
        entities = query_all("SELECT * FROM monitored_entities WHERE is_active = 1")

    for e in entities:
        e["keywords"] = json.loads(e["keywords"]) if isinstance(e.get("keywords"), str) and e.get("keywords") else []

    if not entities:
        return {"success": True, "collected": 0, "message": "Nenhuma entidade ativa"}

    total_collected = 0
    strategy_counts = {"google_news": 0, "open_web": 0}

    for entity in entities:
        search_terms = " OR ".join([entity["name"]] + (entity.get("keywords") or []))
        all_results: list[google_search.SearchResult] = []

        for platform in SOCIAL_PLATFORMS:
            search_query = f"{platform['prefix']} {search_terms} Goiás"
            platform_results: list[google_search.SearchResult] = []
            platform_seen: set[str] = set()

            # Strategy 1: Google News for social links indexed there.
            try:
                news_results = google_search.search_google_news(search_query, limit=3)
                for item in news_results:
                    if item.url in platform_seen:
                        continue
                    platform_seen.add(item.url)
                    platform_results.append(item)
                strategy_counts["google_news"] += len(news_results)
            except Exception as exc:
                print(f"[GoogleNews] Error {platform['label']}/{entity['name']}: {exc}")

            # Strategy 2: open web fallback/expansion when few new links remain.
            news_urls = [r.url for r in platform_results if r.url]
            existing_after_news = _existing_url_set(news_urls)
            unseen_after_news = [r for r in platform_results if r.url not in existing_after_news]
            if len(unseen_after_news) < 2:
                try:
                    web_results = google_search.search_open_web(search_query, limit=5)
                    for item in web_results:
                        if item.url in platform_seen:
                            continue
                        platform_seen.add(item.url)
                        platform_results.append(item)
                    strategy_counts["open_web"] += len(web_results)
                except Exception as exc:
                    print(f"[OpenWeb] Error {platform['label']}/{entity['name']}: {exc}")

            all_results.extend(platform_results)

        seen = set()
        results = []
        for r in all_results:
            if r.url and r.url not in seen:
                seen.add(r.url)
                results.append(r)

        if not results:
            continue

        urls = [r.url for r in results if r.url]
        existing_urls = _existing_url_set(urls)

        new_results = [r for r in results if r.url not in existing_urls]
        if not new_results:
            continue

        with open("prompts/social_classifier.txt", encoding="utf-8") as f:
            base_prompt = f.read().replace("{{entity_name}}", entity["name"])

        for result in new_results:
            text_content = (result.markdown or result.description or result.title)[:3000]
            resp = requests.post(
                "https://ai.gateway.lovable.dev/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {LOVABLE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "google/gemini-2.5-flash",
                    "messages": [
                        {"role": "system", "content": base_prompt},
                        {
                            "role": "user",
                            "content": f"Título: {result.title}\nURL: {result.url}\nConteúdo:\n{text_content}",
                        },
                    ],
                    "temperature": 0.1,
                },
                timeout=30,
            )

            if not resp.ok:
                continue

            raw_content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            cleaned = re.sub(r"```json\n?|```\n?", "", raw_content).strip()
            try:
                classified = json.loads(cleaned)
            except json.JSONDecodeError:
                continue

            merged_mentions = ai_classifier.enrich_people_mentioned(
                classified.get("people_mentioned") if isinstance(classified, dict) else [],
                title=classified.get("title") or result.title,
                content=classified.get("content") or text_content,
                entity_name=entity["name"],
            )
            classified["people_mentioned"] = merged_mentions

            if not classified.get("relevant"):
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
                        f"Mídia negativa (social): {entity['name']}",
                        classified.get("title") or result.title,
                        "warning",
                    ),
                )

    msg = (
        "Busca social concluída com 2 estratégias: "
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
