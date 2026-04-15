"""Web news collection agent.

Searches the web for news about monitored entities using Firecrawl or ScrapingBee,
then classifies each result with AI and stores new items in Supabase.
"""
from __future__ import annotations
from urllib.parse import urlparse

from config import FIRECRAWL_API_KEY, SCRAPINGBEE_API_KEY
from supabase_client import get_service_client
from tools import firecrawl, scrapingbee, ai_classifier


def run(entity_id: str | None = None, user_id: str | None = None) -> dict:
    """Run the web news collection agent.

    Args:
        entity_id: Optional specific entity UUID to limit collection.
        user_id: Optional user UUID for generating alerts.

    Returns:
        dict with keys: success, collected, message.
    """
    if not FIRECRAWL_API_KEY and not SCRAPINGBEE_API_KEY:
        return {"success": False, "error": "Nenhum crawler configurado (Firecrawl ou ScrapingBee)"}

    supa = get_service_client()

    query = supa.table("monitored_entities").select("*").eq("is_active", True)
    if entity_id:
        query = query.eq("id", entity_id)

    result = query.execute()
    entities = result.data or []

    if not entities:
        return {"success": True, "collected": 0, "message": "Nenhuma entidade ativa"}

    total_collected = 0
    firecrawl_exhausted = False
    used_fallback = False

    for entity in entities:
        search_terms = " OR ".join([entity["name"]] + (entity.get("keywords") or []))
        search_query = f"{search_terms} Goiás notícia"

        results = []
        search_source = "firecrawl"

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
                search_source = "scrapingbee"
                used_fallback = True
            except Exception as exc:
                print(f"[ScrapingBee] Error for {entity['name']}: {exc}")
                continue

        if not results:
            continue

        urls = [r.url for r in results if r.url]
        existing_resp = supa.table("news_items").select("source_url").in_("source_url", urls).execute()
        existing_urls = {row["source_url"] for row in (existing_resp.data or [])}
        new_results = [r for r in results if r.url not in existing_urls]

        if not new_results:
            continue

        for result in new_results:
            text_content = result.markdown or result.description or result.title
            classified = ai_classifier.classify_news(
                text_content, result.title, result.url, entity["name"]
            )

            if not classified or not classified.get("relevant"):
                continue

            try:
                source_name = urlparse(result.url).hostname.replace("www.", "")
            except Exception:
                source_name = ""

            insert_resp = supa.table("news_items").insert({
                "title": classified.get("title") or result.title,
                "content": classified.get("content") or result.description or None,
                "source_url": result.url,
                "source_name": source_name,
                "entity_id": entity["id"],
                "sentiment": classified.get("sentiment", "neutro"),
                "classification": classified.get("classification", "outro"),
                "people_mentioned": classified.get("people_mentioned") or [],
            }).execute()

            if insert_resp.data:
                total_collected += 1
                print(f"Collected: {classified.get('title') or result.title}")

                negative = (
                    classified.get("sentiment") == "negativo"
                    or classified.get("classification") == "midia_negativa"
                )
                if negative and user_id:
                    supa.table("alerts").insert({
                        "title": f"Mídia negativa: {entity['name']}",
                        "message": classified.get("title") or result.title,
                        "alert_type": "warning",
                        "user_id": user_id,
                        "news_item_id": None,
                    }).execute()

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
