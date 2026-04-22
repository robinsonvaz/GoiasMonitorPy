"""Social media news collection agent (local MySQL storage)."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any
from urllib.parse import urlparse

import requests

from config import FIRECRAWL_API_KEY, SCRAPINGBEE_API_KEY, LOVABLE_API_KEY
from db import query_all, execute
from tools import firecrawl, scrapingbee

SOCIAL_PLATFORMS = [
    {"prefix": "site:x.com", "label": "X/Twitter"},
    {"prefix": "site:instagram.com", "label": "Instagram"},
    {"prefix": "site:facebook.com", "label": "Facebook"},
]


def run(entity_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
    if not FIRECRAWL_API_KEY and not SCRAPINGBEE_API_KEY:
        return {"success": False, "error": "Nenhum crawler configurado (Firecrawl ou ScrapingBee)"}

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
    firecrawl_exhausted = False
    used_fallback = False

    for entity in entities:
        search_terms = " OR ".join([entity["name"]] + (entity.get("keywords") or []))
        all_results = []

        for platform in SOCIAL_PLATFORMS:
            search_query = f"{platform['prefix']} {search_terms} Goiás"
            platform_results = []

            if FIRECRAWL_API_KEY and not firecrawl_exhausted:
                try:
                    hits, exhausted = firecrawl.search(FIRECRAWL_API_KEY, search_query, limit=3)
                    if exhausted:
                        firecrawl_exhausted = True
                    else:
                        platform_results = hits
                except Exception as exc:
                    print(f"[Firecrawl] Error {platform['label']}/{entity['name']}: {exc}")

            if not platform_results and SCRAPINGBEE_API_KEY:
                try:
                    platform_results = scrapingbee.search(SCRAPINGBEE_API_KEY, search_query, limit=3)
                    used_fallback = True
                except Exception as exc:
                    print(f"[ScrapingBee] Error {platform['label']}/{entity['name']}: {exc}")

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

    msg = None
    if firecrawl_exhausted:
        if used_fallback:
            msg = "Créditos Firecrawl esgotados. ScrapingBee utilizado como alternativa."
        else:
            msg = "Créditos Firecrawl esgotados e ScrapingBee indisponível."

    return {
        "success": True,
        "collected": total_collected,
        "credits_exhausted": firecrawl_exhausted,
        "fallback_used": used_fallback,
        "message": msg,
    }
