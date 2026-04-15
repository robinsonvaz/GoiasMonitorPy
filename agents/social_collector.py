"""Social media news collection agent.

Searches X/Twitter, Instagram, and Facebook for mentions of monitored entities
using Firecrawl or ScrapingBee, then classifies results with AI.
"""
from __future__ import annotations
from urllib.parse import urlparse

from config import FIRECRAWL_API_KEY, SCRAPINGBEE_API_KEY
from supabase_client import get_service_client
from tools import firecrawl, scrapingbee, ai_classifier

SOCIAL_PLATFORMS = [
    {"prefix": "site:x.com", "label": "X/Twitter"},
    {"prefix": "site:instagram.com", "label": "Instagram"},
    {"prefix": "site:facebook.com", "label": "Facebook"},
]


def run(entity_id: str | None = None, user_id: str | None = None) -> dict:
    """Run the social media news collection agent.

    Args:
        entity_id: Optional specific entity UUID to limit collection.
        user_id: Optional user UUID for generating alerts.

    Returns:
        dict with keys: success, collected, credits_exhausted, message.
    """
    if not FIRECRAWL_API_KEY and not SCRAPINGBEE_API_KEY:
        return {"success": False, "error": "Nenhum crawler configurado (Firecrawl ou ScrapingBee)"}

    supa = get_service_client()

    db_query = supa.table("monitored_entities").select("*").eq("is_active", True)
    if entity_id:
        db_query = db_query.eq("id", entity_id)

    result = db_query.execute()
    entities = result.data or []

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
            search_source = "firecrawl"

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
                    search_source = "scrapingbee"
                    used_fallback = True
                except Exception as exc:
                    print(f"[ScrapingBee] Error {platform['label']}/{entity['name']}: {exc}")

            all_results.extend(platform_results)

        # Deduplicate by URL
        seen: set[str] = set()
        results = []
        for r in all_results:
            if r.url and r.url not in seen:
                seen.add(r.url)
                results.append(r)

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

            # Use social classifier prompt
            import json, re, requests as req
            from config import LOVABLE_API_KEY
            truncated = text_content[:3000]

            with open("prompts/social_classifier.txt", encoding="utf-8") as f:
                system_prompt = f.read().replace("{{entity_name}}", entity["name"])

            resp = req.post(
                "https://ai.gateway.lovable.dev/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {LOVABLE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "google/gemini-2.5-flash",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": f"Título: {result.title}\nURL: {result.url}\nConteúdo:\n{truncated}",
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
                print(f"Collected (social): {classified.get('title') or result.title}")

                negative = (
                    classified.get("sentiment") == "negativo"
                    or classified.get("classification") == "midia_negativa"
                )
                if negative and user_id:
                    supa.table("alerts").insert({
                        "title": f"Mídia negativa (social): {entity['name']}",
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
        "credits_exhausted": firecrawl_exhausted,
        "fallback_used": used_fallback,
        "message": msg,
    }
