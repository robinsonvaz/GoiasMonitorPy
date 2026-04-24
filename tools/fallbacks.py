"""Fallback collection utilities: RSS feeds, Google Alerts (RSS) and lightweight extraction.

This module implements a simple, prioritized collector using free sources:
- RSS feeds (config.RSS_FEEDS)
- Google Alerts via RSS (config.GOOGLE_ALERTS_RSS)
- existing search fallbacks (tools.google_search)
- optional article extraction via `trafilatura` when available
"""
from __future__ import annotations

from html import unescape
import re
from typing import List
import time
import unicodedata
import requests

import feedparser

from config import RSS_FEEDS, GOOGLE_ALERTS_RSS
from tools.google_search import SearchResult

try:
    import trafilatura
except Exception:
    trafilatura = None


_TERM_STOPWORDS = {"a", "as", "o", "os", "da", "das", "de", "do", "dos", "e", "em", "na", "nas", "no", "nos"}
_WEAK_MATCH_TOKENS = {
    "deputado",
    "deputada",
    "estado",
    "estadual",
    "federal",
    "goias",
    "goiano",
    "goiana",
    "governo",
    "ministerio",
    "municipal",
    "prefeitura",
    "presidente",
    "publica",
    "publico",
    "secretaria",
    "secretario",
    "secretariao",
    "secretariaa",
    "senador",
    "vice",
    "go",
}


def _make_result(url: str, title: str, description: str = "") -> SearchResult:
    return SearchResult(url=url, title=title, description=description)


def _normalize_text(value: str) -> str:
    text = unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _matches_filter_terms(title: str, summary: str, filter_terms: List[str] | None) -> bool:
    if not filter_terms:
        return True

    hay = _normalize_text(f"{title}\n{summary}")
    if not hay:
        return False

    hay_tokens = set(hay.split())
    compact_hay = hay.replace(" ", "")

    for raw_term in filter_terms:
        normalized_term = _normalize_text(raw_term)
        if not normalized_term:
            continue

        if normalized_term in hay:
            return True

        compact_term = normalized_term.replace(" ", "")
        if compact_term and compact_term in compact_hay:
            return True

        term_tokens = [token for token in normalized_term.split() if token not in _TERM_STOPWORDS]
        if not term_tokens:
            continue

        strong_term_tokens = [
            token for token in term_tokens
            if token not in _WEAK_MATCH_TOKENS and len(token) > 2
        ]

        overlap = sum(1 for token in term_tokens if token in hay_tokens)
        strong_overlap = sum(1 for token in strong_term_tokens if token in hay_tokens)

        if strong_term_tokens and strong_overlap == 0:
            continue

        if len(strong_term_tokens) <= 1 and overlap >= 1:
            return True

        if len(term_tokens) > 1 and overlap >= min(2, len(term_tokens)):
            return True

    return False


def _matches_entity_tags(title: str, summary: str, tags: List[str] | None) -> bool:
    """Stricter matcher used for Google Alerts validation by entity tags.

    A match requires at least one meaningful tag hit in title/summary.
    """
    if not tags:
        return False

    # Google Alerts often includes noisy snippets in summary; prioritize title matching.
    title_hay = _normalize_text(title)
    summary_hay = _normalize_text(summary)
    hay = title_hay or summary_hay
    if not hay:
        return False

    hay_tokens = set(hay.split())
    compact_hay = hay.replace(" ", "")

    for raw_tag in tags:
        normalized_tag = _normalize_text(raw_tag)
        if not normalized_tag:
            continue

        if normalized_tag in hay:
            return True

        compact_tag = normalized_tag.replace(" ", "")
        if compact_tag and compact_tag in compact_hay:
            return True

        tag_tokens = [token for token in normalized_tag.split() if token not in _TERM_STOPWORDS and len(token) > 2]
        strong_tokens = [token for token in tag_tokens if token not in _WEAK_MATCH_TOKENS]
        if not strong_tokens:
            continue

        strong_overlap = sum(1 for token in strong_tokens if token in hay_tokens)
        if len(strong_tokens) == 1 and strong_overlap == 1:
            return True
        if len(strong_tokens) > 1 and strong_overlap >= min(2, len(strong_tokens)):
            return True

    return False


def fetch_rss_entries(
    feed_urls: List[str],
    filter_terms: List[str] | None = None,
    limit: int = 10,
    tag_terms: List[str] | None = None,
) -> List[SearchResult]:
    """Fetch and filter entries from a list of RSS/Atom URLs.

    filter_terms: if provided, only return entries where any term appears in title/summary.
    """
    results: List[SearchResult] = []
    seen: set[str] = set()
    terms = [t.lower() for t in (filter_terms or [])]

    for feed_url in feed_urls or []:
        try:
            parsed = feedparser.parse(feed_url)
        except Exception:
            continue

        entries = getattr(parsed, "entries", []) or []
        for e in entries:
            link = (e.get("link") or "").strip()
            if not link or link in seen:
                continue
            title = (e.get("title") or "").strip()
            summary = (e.get("summary") or e.get("description") or "").strip()
            if tag_terms is not None and not _matches_entity_tags(title, summary, tag_terms):
                continue
            if not _matches_filter_terms(title, summary, terms):
                continue

            seen.add(link)
            results.append(_make_result(link, title or link, summary))
            if len(results) >= limit:
                return results
        # be polite between feed calls
        time.sleep(0.2)

    return results


def extract_article_text(url: str) -> str | None:
    """Attempt to extract article body using trafilatura when available."""
    if trafilatura is None:
        return None
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        return text
    except Exception:
        return None


def _merge_unique_results(*groups: List[SearchResult], limit: int) -> List[SearchResult]:
    results: List[SearchResult] = []
    seen: set[str] = set()

    for group in groups:
        for item in group:
            if not item.url or item.url in seen:
                continue
            seen.add(item.url)
            results.append(item)
            if len(results) >= limit:
                return results

    return results


def collect_for_entity(entity: dict, max_results: int = 8) -> List[SearchResult]:
    """Collect candidate articles for an entity using prioritized free sources.

    Order: configured RSS feeds -> Google Alerts RSS -> fall back to nothing (search handled elsewhere)
    """
    name = (entity.get("name") or "").strip()
    keywords = []
    try:
        kws = entity.get("keywords") or []
        if isinstance(kws, str):
            # stored as JSON string in DB
            import json

            kws = json.loads(kws) if kws else []
        keywords = [k for k in kws if k]
    except Exception:
        keywords = []

    terms = [name] + keywords
    terms = [t for t in terms if t]

    entity_google_alert_feed = (entity.get("google_alert_rss_url") or "").strip()
    entity_google_alert_feeds = [entity_google_alert_feed] if entity_google_alert_feed else []

    # 1) Google Alerts are validated using entity tags (keywords) first.
    tag_terms = keywords if keywords else [name]
    entity_ga_hits = fetch_rss_entries(
        entity_google_alert_feeds,
        filter_terms=terms,
        tag_terms=tag_terms,
        limit=max_results,
    )
    ga_hits = fetch_rss_entries(
        GOOGLE_ALERTS_RSS,
        filter_terms=terms,
        tag_terms=tag_terms,
        limit=max_results,
    )
    rss_hits = fetch_rss_entries(
        RSS_FEEDS,
        filter_terms=terms,
        tag_terms=tag_terms,
        limit=max_results,
    )
    merged_hits = _merge_unique_results(entity_ga_hits, ga_hits, rss_hits, limit=max_results)
    if merged_hits:
        return merged_hits

    # 3) Nothing found here — return empty list so caller can run search fallbacks
    return []
