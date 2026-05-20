"""Robust web search and capture pipeline for news collection."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import json
import random
import re
import threading
import time
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import requests

from config import (
    JINA_API_KEY,
    PLAYWRIGHT_ENABLED,
    SEARCHAPI_API_KEY,
    SEARCHAPI_ENABLED,
    SERPAPI_KEY,
    SERPER_API_KEY,
    TAVILY_API_KEY,
    WEB_PROVIDER_COOLDOWN_SECONDS,
)

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # type: ignore[import-not-found]
    from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
except Exception:
    sync_playwright = None
    PlaywrightTimeoutError = Exception

try:
    from googlesearch import search as _google_python_search
except Exception:
    _google_python_search = None

try:
    from ddgs import DDGS

    try:
        # Keep ddgs stable across primp profile changes.
        from ddgs.http_client import HttpClient as _DDGSHttpClient

        _DDGSHttpClient._impersonates = ("random",)
    except Exception:
        pass
except Exception:
    DDGS = None


USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_0) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
)

_MIN_QUERY_INTERVAL_SECONDS = 1.3
_MAX_QUERY_INTERVAL_SECONDS = 3.2
_provider_blocked_until: dict[str, float] = {}
_state_lock = threading.Lock()
_last_query_ts = 0.0


@dataclass
class SearchResult:
    url: str
    title: str
    description: str = field(default="")
    markdown: str = field(default="")
    published_at: datetime | None = field(default=None)


@dataclass
class CapturedArticle:
    text: str | None = field(default=None)
    published_at: datetime | None = field(default=None)


def _throttle() -> None:
    global _last_query_ts
    now = time.monotonic()
    elapsed = now - _last_query_ts
    target_gap = random.uniform(_MIN_QUERY_INTERVAL_SECONDS, _MAX_QUERY_INTERVAL_SECONDS)
    if elapsed < target_gap:
        time.sleep(target_gap - elapsed)
    _last_query_ts = time.monotonic()


def _normalize_url(url: str) -> str:
    return (url or "").strip()


def _retry_after_seconds(response: requests.Response) -> float:
    retry_after = (response.headers.get("Retry-After") or "").strip()
    if retry_after.isdigit():
        return float(retry_after)
    return float(WEB_PROVIDER_COOLDOWN_SECONDS)


def _is_blocked(provider: str) -> bool:
    with _state_lock:
        return time.monotonic() < _provider_blocked_until.get(provider, 0.0)


def _block_provider(provider: str, seconds: float) -> None:
    if seconds <= 0:
        return
    with _state_lock:
        _provider_blocked_until[provider] = max(
            _provider_blocked_until.get(provider, 0.0),
            time.monotonic() + seconds,
        )


def _mark_response(provider: str, response: requests.Response) -> None:
    if response.status_code in (403, 429):
        _block_provider(provider, _retry_after_seconds(response))


def _request(
    provider: str,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> requests.Response | None:
    if _is_blocked(provider):
        return None

    _throttle()
    merged_headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
    }
    if headers:
        merged_headers.update(headers)

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=merged_headers,
            params=params,
            json=json_body,
            timeout=timeout,
        )
    except requests.RequestException:
        _block_provider(provider, 20.0)
        return None

    _mark_response(provider, response)
    if not response.ok:
        return None
    return response


def _sanitize_title(value: str) -> str:
    """Remove HTML tags and decode entities from title."""
    cleaned = unescape(value or "")
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _merge_unique(base: list[SearchResult], extra: list[SearchResult], limit: int) -> list[SearchResult]:
    seen = {_normalize_url(item.url) for item in base if item.url}
    merged = list(base)
    for item in extra:
        url = _normalize_url(item.url)
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def _parse_result_list(raw_results: list[dict[str, Any]] | None, limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    for raw in raw_results or []:
        url = _normalize_url(raw.get("url") or raw.get("link") or raw.get("href") or "")
        if not url:
            continue
        title = _sanitize_title(raw.get("title") or url)
        description = (
            raw.get("content")
            or raw.get("description")
            or raw.get("snippet")
            or raw.get("body")
            or ""
        )
        published_at = _coerce_datetime(
            raw.get("published_at")
            or raw.get("published")
            or raw.get("publishedAt")
            or raw.get("pubDate")
            or raw.get("date")
            or raw.get("time")
        )
        results.append(SearchResult(url=url, title=title, description=description, published_at=published_at))
        if len(results) >= limit:
            break
    return results


def _normalize_datetime(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return _normalize_datetime(value)

    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 1_000_000_000_000:
            timestamp /= 1000.0
        if timestamp <= 0:
            return None
        try:
            return datetime.utcfromtimestamp(timestamp)
        except Exception:
            return None

    text = str(value).strip()
    if not text:
        return None

    iso_candidate = text.replace("Z", "+00:00")
    if "T" not in iso_candidate and re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", iso_candidate):
        iso_candidate = iso_candidate.replace(" ", "T", 1)
    try:
        return _normalize_datetime(datetime.fromisoformat(iso_candidate))
    except Exception:
        pass

    try:
        return _normalize_datetime(parsedate_to_datetime(text))
    except Exception:
        pass

    simple_match = re.search(r"(\d{4}-\d{2}-\d{2})(?:[T\s](\d{2}:\d{2}(?::\d{2})?))?", text)
    if not simple_match:
        return None
    date_part = simple_match.group(1)
    time_part = simple_match.group(2) or "00:00:00"
    if len(time_part) == 5:
        time_part = f"{time_part}:00"
    try:
        return datetime.fromisoformat(f"{date_part}T{time_part}")
    except Exception:
        return None


def _json_ld_publication_date(html: str) -> datetime | None:
    for script in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        payload = unescape(script or "").strip()
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except Exception:
            continue

        stack: list[Any] = [parsed]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                dt = _coerce_datetime(
                    node.get("datePublished")
                    or node.get("dateModified")
                    or node.get("dateCreated")
                    or node.get("uploadDate")
                )
                if dt:
                    return dt
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return None


def _extract_published_at_from_html(url: str) -> datetime | None:
    response = _request("article_meta", "GET", url, timeout=20)
    if response is None:
        return None

    html = response.text[:400000]
    if not html:
        return None

    meta_patterns = (
        r'<meta[^>]+(?:property|name)=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+(?:property|name)=["\']og:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+(?:property|name)=["\']publishdate["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+(?:property|name)=["\']pubdate["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+(?:property|name)=["\']date["\'][^>]+content=["\']([^"\']+)["\']',
    )
    for pattern in meta_patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if not match:
            continue
        dt = _coerce_datetime(match.group(1))
        if dt:
            return dt

    time_match = re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if time_match:
        dt = _coerce_datetime(time_match.group(1))
        if dt:
            return dt

    return _json_ld_publication_date(html)


def _search_tavily(query: str, limit: int, *, news_mode: bool) -> list[SearchResult]:
    if not TAVILY_API_KEY:
        return []
    response = _request(
        "tavily",
        "POST",
        "https://api.tavily.com/search",
        headers={"Content-Type": "application/json"},
        json_body={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "topic": "news" if news_mode else "general",
            "search_depth": "advanced",
            "max_results": max(1, min(limit, 10)),
            "include_answer": False,
            "include_raw_content": False,
        },
    )
    if response is None:
        return []
    data = response.json()
    return _parse_result_list(data.get("results"), limit)


def _search_serper(query: str, limit: int, *, news_mode: bool) -> list[SearchResult]:
    if not SERPER_API_KEY:
        return []
    endpoint = "https://google.serper.dev/news" if news_mode else "https://google.serper.dev/search"
    response = _request(
        "serper",
        "POST",
        endpoint,
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json_body={"q": query, "num": max(1, min(limit, 10)), "gl": "br", "hl": "pt-br"},
    )
    if response is None:
        return []
    data = response.json()
    block = data.get("news") if news_mode else data.get("organic")
    return _parse_result_list(block, limit)


def _search_serpapi(query: str, limit: int, *, news_mode: bool) -> list[SearchResult]:
    if not SERPAPI_KEY:
        return []
    params: dict[str, Any] = {
        "api_key": SERPAPI_KEY,
        "engine": "google",
        "q": query,
        "gl": "br",
        "hl": "pt-br",
        "num": max(1, min(limit, 10)),
    }
    if news_mode:
        params["tbm"] = "nws"
    response = _request("serpapi", "GET", "https://serpapi.com/search.json", params=params)
    if response is None:
        return []
    data = response.json()
    block = data.get("news_results") if news_mode else data.get("organic_results")
    return _parse_result_list(block, limit)


def _search_searchapi(query: str, limit: int, *, news_mode: bool) -> list[SearchResult]:
    if not SEARCHAPI_ENABLED or not SEARCHAPI_API_KEY:
        return []
    params: dict[str, Any] = {
        "engine": "google",
        "q": query,
        "api_key": SEARCHAPI_API_KEY,
        "gl": "br",
        "hl": "pt-br",
        "num": max(1, min(limit, 10)),
    }
    if news_mode:
        params["tbm"] = "nws"
    response = _request("searchapi", "GET", "https://www.searchapi.io/api/v1/search", params=params)
    if response is None:
        return []
    data = response.json()
    block = data.get("news_results") if news_mode else data.get("organic_results")
    return _parse_result_list(block, limit)


def _search_google_python(query: str, limit: int, *, news_mode: bool) -> list[SearchResult]:
    if _google_python_search is None:
        return []
    if _is_blocked("google_python"):
        return []

    weekly_query = f"{query} when:7d" if news_mode else query
    results: list[SearchResult] = []
    try:
        _throttle()
        for url in _google_python_search(weekly_query, num_results=limit, lang="pt", sleep_interval=2):
            raw_url = getattr(url, "url", url)
            normalized = _normalize_url(str(raw_url))
            if not normalized:
                continue
            results.append(SearchResult(url=normalized, title=normalized))
            if len(results) >= limit:
                break
    except Exception:
        _block_provider("google_python", 30.0)
        return []
    return results


def _search_ddgs(query: str, limit: int, *, news_mode: bool) -> list[SearchResult]:
    if DDGS is None:
        return []
    if _is_blocked("ddgs"):
        return []

    results: list[SearchResult] = []
    try:
        _throttle()
        with DDGS() as ddgs:
            if news_mode:
                hits = ddgs.news(query, region="br-pt", max_results=limit, timelimit="w")
            else:
                hits = ddgs.text(query, region="br-pt", max_results=limit, safesearch="off", timelimit="w")

            for item in hits or []:
                url = _normalize_url(item.get("url") or item.get("href") or "")
                if not url:
                    continue
                title = _sanitize_title(item.get("title") or url)
                description = item.get("body") or item.get("snippet") or ""
                published_at = _coerce_datetime(item.get("date") or item.get("published"))
                results.append(SearchResult(url=url, title=title, description=description, published_at=published_at))
                if len(results) >= limit:
                    break
    except Exception:
        _block_provider("ddgs", 30.0)
        return []
    return results


def _search_playwright(query: str, limit: int, *, news_mode: bool) -> list[SearchResult]:
    if not PLAYWRIGHT_ENABLED or sync_playwright is None:
        return []
    if _is_blocked("playwright_search"):
        return []

    search_query = f"{query} when:7d" if news_mode else query
    target_url = f"https://www.google.com/search?q={quote_plus(search_query)}&hl=pt-BR&gl=BR"
    if news_mode:
        target_url += "&tbm=nws"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
            )
            page = context.new_page()
            page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(random.randint(450, 1050))
            nodes = page.query_selector_all("a:has(h3)")
            results: list[SearchResult] = []
            for node in nodes:
                href = (node.get_attribute("href") or "").strip()
                if not href:
                    continue
                if href.startswith("/url?"):
                    parsed_qs = parse_qs(urlparse(href).query)
                    href = (parsed_qs.get("q") or [""])[0]
                if not href or not href.startswith("http"):
                    continue
                title_node = node.query_selector("h3")
                title = (title_node.inner_text().strip() if title_node else href)[:320]
                title = _sanitize_title(title)
                results.append(SearchResult(url=href, title=title))
                if len(results) >= limit:
                    break
            context.close()
            browser.close()
            return results
    except PlaywrightTimeoutError:
        _block_provider("playwright_search", 45.0)
        return []
    except Exception:
        _block_provider("playwright_search", 60.0)
        return []


def _search_with_chain(query: str, limit: int, *, news_mode: bool) -> list[SearchResult]:
    results: list[SearchResult] = []
    for provider in (
        _search_tavily,
        _search_serper,
        _search_serpapi,
        _search_searchapi,
        _search_google_python,
        _search_ddgs,
        _search_playwright,
    ):
        if len(results) >= limit:
            break
        try:
            batch = provider(query, limit=limit, news_mode=news_mode)
        except Exception:
            batch = []
        results = _merge_unique(results, batch, limit)
    return results


def _clean_captured_text(raw: str, *, max_chars: int = 120000) -> str:
    cleaned = unescape(raw or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_chars]


def _capture_with_jina(url: str) -> str | None:
    if not JINA_API_KEY:
        return None
    normalized = _normalize_url(url)
    if not normalized:
        return None
    if normalized.startswith("https://"):
        jina_url = "https://r.jina.ai/http://" + normalized[len("https://"):]
    elif normalized.startswith("http://"):
        jina_url = "https://r.jina.ai/http://" + normalized[len("http://"):]
    else:
        jina_url = f"https://r.jina.ai/http://{normalized}"

    response = _request(
        "jina_extract",
        "GET",
        jina_url,
        headers={"Authorization": f"Bearer {JINA_API_KEY}"},
        timeout=35,
    )
    if response is None:
        return None
    text = _clean_captured_text(response.text)
    return text or None


def _capture_with_playwright(url: str) -> str | None:
    if not PLAYWRIGHT_ENABLED or sync_playwright is None:
        return None
    if _is_blocked("playwright_capture"):
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=35000)
            page.wait_for_timeout(random.randint(500, 1200))
            text = page.locator("body").inner_text(timeout=10000)
            context.close()
            browser.close()
            cleaned = _clean_captured_text(text)
            return cleaned or None
    except PlaywrightTimeoutError:
        _block_provider("playwright_capture", 45.0)
        return None
    except Exception:
        _block_provider("playwright_capture", 60.0)
        return None


def capture_article_text(url: str, summary_mode: bool = True) -> str | None:
    """Capture article text with Jina first and Playwright as fallback."""
    return capture_article_details(url, summary_mode=summary_mode).text


def capture_article_details(url: str, summary_mode: bool = True) -> CapturedArticle:
    """Capture article body and publication date when available."""
    captured = _capture_with_jina(url)
    if not captured:
        captured = _capture_with_playwright(url)
    published_at = _extract_published_at_from_html(url)

    if not captured:
        return CapturedArticle(text=None, published_at=published_at)
    if summary_mode:
        captured = captured[:2200]
    return CapturedArticle(text=captured, published_at=published_at)


def search_google_news(query: str, limit: int = 5) -> list[SearchResult]:
    """Primary news search: Tavily with fallback providers chain."""
    news_query = f"{query} site:globo.com OR site:g1.globo.com OR site:news.google.com"
    primary = _search_with_chain(news_query, limit=limit, news_mode=True)
    if len(primary) >= limit:
        return primary
    broader = _search_with_chain(query, limit=limit, news_mode=True)
    return _merge_unique(primary, broader, limit)


def search_open_web(query: str, limit: int = 5) -> list[SearchResult]:
    """Open web fallback/expansion chain."""
    return _search_with_chain(query, limit=limit, news_mode=False)