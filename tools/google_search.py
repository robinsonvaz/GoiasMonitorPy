"""Google search strategies for news collection."""
from __future__ import annotations

from dataclasses import dataclass, field
import random
import time
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import quote_plus

import requests
from ddgs import DDGS
from googlesearch import search as google_search

try:
    # Work around ddgs/primp profile drift that emits
    # "Impersonate 'chrome_130' does not exist, using 'random'".
    from ddgs.http_client import HttpClient as _DDGSHttpClient

    _DDGSHttpClient._impersonates = ("random",)
except Exception:
    # Keep search working even if ddgs internals change.
    pass

# Keep query cadence slower to reduce provider throttling.
MIN_QUERY_INTERVAL_SECONDS = 2.5
MAX_QUERY_INTERVAL_SECONDS = 5.5
BACKOFF_STEPS_SECONDS = (6.0, 12.0, 20.0)
_last_query_ts = 0.0


@dataclass
class SearchResult:
    url: str
    title: str
    description: str = field(default="")
    markdown: str = field(default="")


def _throttle() -> None:
    global _last_query_ts
    now = time.monotonic()
    elapsed = now - _last_query_ts
    target_gap = random.uniform(MIN_QUERY_INTERVAL_SECONDS, MAX_QUERY_INTERVAL_SECONDS)
    if elapsed < target_gap:
        time.sleep(target_gap - elapsed)
    _last_query_ts = time.monotonic()


def _is_429_error(exc: Exception) -> bool:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code == 429
    return "429" in str(exc)


def _merge_unique(base: list[SearchResult], extra: list[SearchResult], limit: int) -> list[SearchResult]:
    seen = {item.url for item in base}
    merged = list(base)
    for item in extra:
        if not item.url or item.url in seen:
            continue
        seen.add(item.url)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def _google_news_rss_search(query: str, limit: int = 5) -> list[SearchResult]:
    """Primary strategy: consume Google News RSS for the query.

    This avoids heavy scraping of SERP pages and is usually more stable.
    """
    encoded_q = quote_plus(query)
    rss_url = (
        "https://news.google.com/rss/search"
        f"?q={encoded_q}+when:7d&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    )
    resp = requests.get(
        rss_url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    items = root.findall("./channel/item")

    results: list[SearchResult] = []

    def _resolve_news_google_url(url: str, title: str, source_name: str) -> str:
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
                allow_redirects=True,
            )
            resolved = str(resp.url or url)
            if "news.google.com/rss/articles/" not in resolved:
                return resolved
        except Exception:
            resolved = url

        # Google News RSS article URLs may remain opaque. Resolve via DDGS using title/source.
        query_base = f'"{title}" {source_name}'.strip()
        try:
            with DDGS() as ddgs:
                for item in ddgs.news(query_base, region="br-pt", max_results=3, timelimit="w") or []:
                    candidate = item.get("url") or item.get("href") or ""
                    if candidate and "news.google.com/rss/articles/" not in candidate:
                        return candidate

                for item in ddgs.text(query_base, region="br-pt", max_results=3, safesearch="off", timelimit="w") or []:
                    candidate = item.get("url") or item.get("href") or ""
                    if candidate and "news.google.com/rss/articles/" not in candidate:
                        return candidate
        except Exception:
            return resolved

        return resolved

    for item in items:
        link = (item.findtext("link") or "").strip()
        if not link:
            continue
        source_name = (item.findtext("source") or "").strip()
        title = unescape((item.findtext("title") or link).strip())
        resolved_link = _resolve_news_google_url(link, title, source_name)
        if "news.google.com/rss/articles/" in resolved_link:
            # Opaque Google URL could not be resolved to publisher URL.
            continue
        description = unescape((item.findtext("description") or "").strip())
        results.append(SearchResult(url=resolved_link, title=title, description=description))
        if len(results) >= limit:
            break
    return results


def _google_search_with_backoff(query: str, limit: int = 5) -> list[SearchResult]:
    last_error: Exception | None = None

    for attempt in range(len(BACKOFF_STEPS_SECONDS) + 1):
        try:
            _throttle()
            results: list[SearchResult] = []
            weekly_query = f"{query} when:7d"
            for url in google_search(weekly_query, num_results=limit, lang="pt", sleep_interval=2):
                if not url:
                    continue
                results.append(SearchResult(url=url, title=url))
            return results
        except Exception as exc:
            last_error = exc
            if not _is_429_error(exc) or attempt >= len(BACKOFF_STEPS_SECONDS):
                break
            delay = BACKOFF_STEPS_SECONDS[attempt] + random.uniform(0.5, 2.0)
            time.sleep(delay)

    if last_error is not None:
        raise RuntimeError(f"Google search failure for query '{query}': {last_error}") from last_error
    return []


def _duckduckgo_search(query: str, limit: int = 5, *, news_mode: bool = False) -> list[SearchResult]:
    results: list[SearchResult] = []
    with DDGS() as ddgs:
        if news_mode:
            hits = ddgs.news(query, region="br-pt", max_results=limit, timelimit="w")
        else:
            hits = ddgs.text(query, region="br-pt", max_results=limit, safesearch="off", timelimit="w")

        for item in hits or []:
            url = item.get("url") or item.get("href") or ""
            if not url:
                continue
            title = item.get("title") or url
            description = item.get("body") or item.get("snippet") or ""
            results.append(SearchResult(url=url, title=title, description=description))
    return results


def _safe_search(query: str, limit: int = 5, *, news_mode: bool = False) -> list[SearchResult]:
    try:
        return _google_search_with_backoff(query, limit=limit)
    except Exception as exc:
        print(f"[GoogleSearch] fallback to DuckDuckGo for query '{query}': {exc}")
        return _duckduckgo_search(query, limit=limit, news_mode=news_mode)


def search_google_news(query: str, limit: int = 5) -> list[SearchResult]:
    """Google News first, then fallback to SERP and DDGS news."""
    results: list[SearchResult] = []

    # Strategy 1 (primary): Google News RSS.
    try:
        results = _google_news_rss_search(query, limit=limit)
        if len(results) >= limit:
            return results
    except Exception as exc:
        print(f"[GoogleNewsRSS] fallback for query '{query}': {exc}")

    # Fallback: SERP + DDGS chain using news-focused query.
    news_query = f"site:news.google.com {query}"
    fallback_results = _safe_search(news_query, limit=limit, news_mode=True)
    if not fallback_results:
        # Broader fallback if the site-filtered query is too restrictive.
        fallback_results = _safe_search(query, limit=limit, news_mode=True)
    return _merge_unique(results, fallback_results, limit)


def search_open_web(query: str, limit: int = 5) -> list[SearchResult]:
    """Strategy 2: general open web search as fallback/expansion."""
    return _safe_search(query, limit=limit, news_mode=False)