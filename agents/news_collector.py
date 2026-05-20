"""Web news collection agent (local MySQL storage)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import threading
import time
import uuid
from typing import Any
from urllib.parse import urlparse

from config import NEWS_COLLECTION_WORKERS
from db import query_all, execute
from tools import ai_classifier, google_search, fallbacks
from tools.news_dedup import build_dedup_fields, find_existing_news_duplicate, normalize_url


_EXTRACTION_CACHE_MAX_ITEMS = 256


def _existing_url_set(urls: list[str]) -> set[str]:
    if not urls:
        return set()
    placeholders = ",".join(["%s"] * len(urls))
    normalized = [normalize_url(url) for url in urls if url]
    existing_rows = query_all(
        f"SELECT source_url_norm FROM news_items WHERE source_url_norm IN ({placeholders})",
        tuple(normalized),
    )
    return {row["source_url_norm"] for row in existing_rows if row.get("source_url_norm")}


def _fallback_classification(result: google_search.SearchResult) -> dict[str, Any]:
    return {
        "title": fallbacks._sanitize_title(result.title or ""),
        "content": result.description or result.markdown or None,
        "classification": "outro",
        "sentiment": "neutro",
        "people_mentioned": [],
        "relevant": True,
        "used_ai_fallback": True,
    }


def _prepare_result_for_classification(
    result: google_search.SearchResult,
    entity_name: str,
    extraction_cache: dict[str, tuple[str, datetime | None]],
    cache_lock: threading.Lock,
) -> dict[str, Any]:
    source_title = fallbacks._sanitize_title(result.title or "") or (result.url or "")
    extraction_started = time.perf_counter()
    full_content = (result.markdown or "").strip()
    published_at = result.published_at
    extraction_cache_hit = False
    extraction_attempted = False

    if (not full_content or not published_at) and result.url:
        extraction_attempted = True
        cache_key = normalize_url(result.url)
        with cache_lock:
            cached_value = extraction_cache.get(cache_key)
            extraction_cache_hit = cached_value is not None

        if cached_value is not None:
            extracted, extracted_published_at = cached_value
        else:
            extracted, extracted_published_at = fallbacks.extract_article_details(result.url, summary_mode=False)

        if not extraction_cache_hit:
            with cache_lock:
                if cache_key not in extraction_cache and len(extraction_cache) >= _EXTRACTION_CACHE_MAX_ITEMS:
                    extraction_cache.pop(next(iter(extraction_cache)))
                extraction_cache[cache_key] = (extracted or "", extracted_published_at)

        if extracted and not full_content:
            full_content = extracted
        if not published_at and extracted_published_at:
            published_at = extracted_published_at
    extraction_time_ms = (time.perf_counter() - extraction_started) * 1000.0

    text_content = full_content or result.description or source_title
    classification_started = time.perf_counter()
    classified = ai_classifier.classify_news(text_content, source_title, result.url, entity_name)
    classification_time_ms = (time.perf_counter() - classification_started) * 1000.0
    used_ai_fallback = False
    if not classified:
        classified = _fallback_classification(result)
        used_ai_fallback = True

    dedup_fields = build_dedup_fields(
        title=source_title,
        content=classified.get("content") or result.description,
        full_text=full_content or text_content,
        source_url=result.url,
    )
    return {
        "result": result,
        "classified": classified,
        "full_content": full_content,
        "text_content": text_content,
        "dedup_fields": dedup_fields,
        "used_ai_fallback": used_ai_fallback,
        "published_at": published_at,
        "extraction_time_ms": extraction_time_ms,
        "classification_time_ms": classification_time_ms,
        "extraction_attempted": extraction_attempted,
        "extraction_cache_hit": extraction_cache_hit,
    }


def run(entity_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
    run_started = time.perf_counter()

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
    fallback_classifications = 0
    strategy_counts = {
        "rss_feeds": 0,
        "google_alerts": 0,
        "local_portals": 0,
        "google_news": 0,
        "open_web": 0,
    }
    extraction_cache: dict[str, tuple[str, datetime | None]] = {}
    cache_lock = threading.Lock()

    for entity in entities:
        entity_started = time.perf_counter()
        perf_metrics = {
            "rss_ms": 0.0,
            "google_news_ms": 0.0,
            "open_web_ms": 0.0,
            "existing_filter_ms": 0.0,
            "prepare_ms": 0.0,
            "extraction_ms": 0.0,
            "classification_ms": 0.0,
            "dedup_check_ms": 0.0,
            "insert_ms": 0.0,
            "alerts_ms": 0.0,
            "extraction_attempts": 0,
            "extraction_cache_hits": 0,
        }

        search_terms = " OR ".join([entity["name"]] + (entity.get("keywords") or []))
        search_query = f"{search_terms} Goiás notícia"

        results: list[google_search.SearchResult] = []
        seen_urls: set[str] = set()

        # Strategy 0 (mandatory): local Goiás portals are the primary capture mechanism.
        rss_started = time.perf_counter()
        try:
            local_results = fallbacks.collect_local_portals_for_entity(entity, max_results=8)
            for item in local_results:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                results.append(item)
            strategy_counts["local_portals"] += len(local_results)

            # Strategy 1 (complementary): entity/global Google Alerts + configured RSS feeds.
            feed_results = fallbacks.collect_alerts_and_feeds_for_entity(entity, max_results=6)
            for item in feed_results:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                results.append(item)
            for item in feed_results:
                if item.source_type in ("google_alert_entity", "google_alert_global"):
                    strategy_counts["google_alerts"] += 1
                elif item.source_type == "rss_manual":
                    strategy_counts["rss_feeds"] += 1
        except Exception as exc:
            print(f"[Local/Feeds] Error for {entity['name']}: {exc}")
        perf_metrics["rss_ms"] += (time.perf_counter() - rss_started) * 1000.0

        # Strategy 2: prioritize Google News results if additional candidates needed.
        google_news_started = time.perf_counter()
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
        perf_metrics["google_news_ms"] += (time.perf_counter() - google_news_started) * 1000.0

        # Strategy 3 (fallback/expansion): if few *new* candidates remain.
        existing_filter_started = time.perf_counter()
        current_urls = [normalize_url(r.url) for r in results if r.url]
        existing_after_news = _existing_url_set(current_urls)
        unseen_after_news = [r for r in results if normalize_url(r.url) not in existing_after_news]
        perf_metrics["existing_filter_ms"] += (time.perf_counter() - existing_filter_started) * 1000.0

        if len(unseen_after_news) < 3:
            open_web_started = time.perf_counter()
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
            perf_metrics["open_web_ms"] += (time.perf_counter() - open_web_started) * 1000.0

        if not results:
            print(f"[Perf] {entity['name']}: nenhum resultado candidato")
            continue

        existing_filter_started = time.perf_counter()
        urls = [normalize_url(r.url) for r in results if r.url]
        existing_urls = _existing_url_set(urls)
        perf_metrics["existing_filter_ms"] += (time.perf_counter() - existing_filter_started) * 1000.0

        new_results = [r for r in results if normalize_url(r.url) not in existing_urls]
        if not new_results:
            print(f"[Perf] {entity['name']}: 0 novos resultados (todos já existentes)")
            continue

        prepared_items: list[dict[str, Any]] = []
        prepare_started = time.perf_counter()
        max_workers = min(NEWS_COLLECTION_WORKERS, len(new_results))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    _prepare_result_for_classification,
                    result,
                    entity["name"],
                    extraction_cache,
                    cache_lock,
                ): result
                for result in new_results
            }
            for future in as_completed(future_map):
                try:
                    prepared = future.result()
                except Exception as exc:
                    result = future_map[future]
                    print(f"[Classification] Error for {result.url}: {exc}")
                    source_title = fallbacks._sanitize_title(result.title or "") or (result.url or "")
                    prepared = {
                        "result": result,
                        "classified": _fallback_classification(result),
                        "full_content": (result.markdown or "").strip(),
                        "text_content": (result.markdown or result.description or source_title),
                        "dedup_fields": build_dedup_fields(
                            title=source_title,
                            content=result.description,
                            full_text=(result.markdown or result.description or source_title),
                            source_url=result.url,
                        ),
                        "used_ai_fallback": True,
                        "published_at": result.published_at,
                        "extraction_time_ms": 0.0,
                        "classification_time_ms": 0.0,
                        "extraction_attempted": False,
                        "extraction_cache_hit": False,
                    }
                prepared_items.append(prepared)
        perf_metrics["prepare_ms"] += (time.perf_counter() - prepare_started) * 1000.0

        for prepared in prepared_items:
            result = prepared["result"]
            classified = prepared["classified"]
            full_content = prepared["full_content"]
            text_content = prepared["text_content"]
            published_at = prepared.get("published_at")
            dedup_fields = prepared["dedup_fields"]
            perf_metrics["extraction_ms"] += float(prepared.get("extraction_time_ms") or 0.0)
            perf_metrics["classification_ms"] += float(prepared.get("classification_time_ms") or 0.0)
            if prepared.get("extraction_attempted"):
                perf_metrics["extraction_attempts"] += 1
            if prepared.get("extraction_cache_hit"):
                perf_metrics["extraction_cache_hits"] += 1

            if prepared["used_ai_fallback"]:
                fallback_classifications += 1

            if not classified.get("relevant"):
                continue

            dedup_started = time.perf_counter()
            existing_duplicate_id = find_existing_news_duplicate(
                source_url=result.url,
                source_url_norm=dedup_fields["source_url_norm"],
                title_norm=dedup_fields["title_norm"],
                content_hash=dedup_fields["content_hash"],
                dedup_key=dedup_fields["dedup_key"],
            )
            perf_metrics["dedup_check_ms"] += (time.perf_counter() - dedup_started) * 1000.0
            if existing_duplicate_id:
                continue

            try:
                source_name = (urlparse(result.url).hostname or "").replace("www.", "")
            except Exception:
                source_name = ""

            news_item_id = str(uuid.uuid4())

            insert_started = time.perf_counter()
            execute(
                """
                INSERT INTO news_items
                (id, entity_id, title, content, full_content, source_url, source_url_norm, source_name,
                 title_norm, content_hash, dedup_key, classification, sentiment,
                 people_mentioned, published_at, collected_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(6), NOW(6))
                """,
                (
                    news_item_id,
                    entity["id"],
                    fallbacks._sanitize_title(result.title or "") or (result.url or ""),
                    classified.get("content") or result.description or None,
                    full_content or text_content,
                    result.url,
                    dedup_fields["source_url_norm"],
                    source_name,
                    dedup_fields["title_norm"],
                    dedup_fields["content_hash"],
                    dedup_fields["dedup_key"],
                    classified.get("classification", "outro"),
                    classified.get("sentiment", "neutro"),
                    json.dumps(classified.get("people_mentioned") or [], ensure_ascii=False),
                    published_at,
                ),
            )
            perf_metrics["insert_ms"] += (time.perf_counter() - insert_started) * 1000.0
            total_collected += 1

            negative = (
                not classified.get("used_ai_fallback")
                and (
                classified.get("sentiment") == "negativo"
                or classified.get("classification") == "midia_negativa"
                )
            )
            if negative and user_id:
                alert_started = time.perf_counter()
                execute(
                    """
                    INSERT INTO alerts
                    (id, user_id, news_item_id, title, message, alert_type, is_read, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 0, NOW(6))
                    """,
                    (
                        str(uuid.uuid4()),
                        user_id,
                        news_item_id,
                        f"Mídia negativa: {entity['name']}",
                        fallbacks._sanitize_title(result.title or "") or (result.url or ""),
                        "warning",
                    ),
                )
                perf_metrics["alerts_ms"] += (time.perf_counter() - alert_started) * 1000.0

        entity_elapsed_ms = (time.perf_counter() - entity_started) * 1000.0
        print(
            f"[Perf] {entity['name']} | total={entity_elapsed_ms:.1f}ms | "
            f"rss={perf_metrics['rss_ms']:.1f} | gnews={perf_metrics['google_news_ms']:.1f} | "
            f"openweb={perf_metrics['open_web_ms']:.1f} | db_filter={perf_metrics['existing_filter_ms']:.1f} | "
            f"prepare={perf_metrics['prepare_ms']:.1f} | extract={perf_metrics['extraction_ms']:.1f} | "
            f"classify={perf_metrics['classification_ms']:.1f} | dedup={perf_metrics['dedup_check_ms']:.1f} | "
            f"insert={perf_metrics['insert_ms']:.1f} | alerts={perf_metrics['alerts_ms']:.1f} | "
            f"cache_hit={perf_metrics['extraction_cache_hits']}/{perf_metrics['extraction_attempts']} | "
            f"new_candidates={len(new_results)}"
        )

    msg = (
        "Busca concluída: "
        f"RSS/Alerts ({strategy_counts['rss_feeds']}) , "
        f"Portais locais ({strategy_counts['local_portals']}) , "
        f"Google News ({strategy_counts['google_news']} resultados) e "
        f"Internet aberta ({strategy_counts['open_web']} resultados)."
    )
    if fallback_classifications:
        msg += f" {fallback_classifications} item(ns) foram salvos sem classificação por IA."

    total_elapsed_ms = (time.perf_counter() - run_started) * 1000.0
    print(
        f"[Perf] coleta_total={total_elapsed_ms:.1f}ms | entidades={len(entities)} | "
        f"coletadas={total_collected} | fallback_ia={fallback_classifications} | "
        f"cache_size={len(extraction_cache)}"
    )

    return {
        "success": True,
        "collected": total_collected,
        "fallback_classifications": fallback_classifications,
        "local_portal_results": strategy_counts["local_portals"],
        "google_news_results": strategy_counts["google_news"],
        "open_web_results": strategy_counts["open_web"],
        "message": msg,
    }
