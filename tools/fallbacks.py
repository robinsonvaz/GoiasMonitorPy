"""Fallback collection utilities: RSS feeds, Google Alerts (RSS) and lightweight extraction.

This module implements a simple, prioritized collector using free sources:
- RSS feeds (config.RSS_FEEDS)
- Google Alerts via RSS (config.GOOGLE_ALERTS_RSS)
- existing search fallbacks (tools.google_search)
- optional article extraction via `trafilatura` when available
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import re
from typing import List
import time
import unicodedata
from urllib.parse import parse_qs, urljoin, urlparse
import requests

import feedparser

from config import RSS_FEEDS, GOOGLE_ALERTS_RSS
from tools import google_search
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
_RELATED_CONTENT_SPLIT_RE = re.compile(
    r"\b(?:leia|veja|confira|entenda|saiba|assista)\s+tamb[eé]m\b|"
    r"\bnot[ií]cias\s+relacionadas\b|"
    r"\bconte[uú]do\s+relacionado\b|"
    r"\bmat[eé]rias\s+relacionadas\b|"
    r"\bmais\s+lidas?\b|"
    r"\bmais\s+do\s+g1\b|"
    r"\brecomendad[oa]s?\b|"
    r"\bveja\s+mais\b|"
    r"\bcontinue\s+lendo\b",
    flags=re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_GOIAS_CONTEXT_MARKERS = (
    "goias",
    "goias.gov.br",
    "go.gov.br",
    "goiana",
    "goiano",
    "goiania",
    "governador de goias",
    "estado de goias",
    "alego",
)
_LOCAL_PORTAL_SOURCES = (
    {
        "name": "Jornal Opção",
        "feed_urls": ("https://www.jornalopcao.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("jornalopcao.com.br",),
        "article_patterns": (),
    },
    {
        "name": "Diário de Goiás",
        "feed_urls": ("https://diariodegoias.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("diariodegoias.com.br",),
        "article_patterns": (),
    },
    {
        "name": "Diário da Manhã",
        "feed_urls": ("https://www.dm.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("dm.com.br",),
        "article_patterns": (),
    },
    {
        "name": "O Hoje",
        "feed_urls": ("https://ohoje.com/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("ohoje.com",),
        "article_patterns": (),
    },
    {
        "name": "Portal 6",
        "feed_urls": ("https://portal6.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("portal6.com.br",),
        "article_patterns": (),
    },
    {
        "name": "Goiás 24 Horas",
        "feed_urls": ("https://goias24horas.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("goias24horas.com.br",),
        "article_patterns": (),
    },
    {
        "name": "Opinião Goiás",
        "feed_urls": ("https://opiniaogoias.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("opiniaogoias.com.br",),
        "article_patterns": (),
    },
    {
        "name": "A Redação",
        "feed_urls": ("https://www.aredacao.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("aredacao.com.br",),
        "article_patterns": (),
    },
    {
        "name": "Diário do Estado",
        "feed_urls": ("https://diariodoestadogo.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("diariodoestadogo.com.br",),
        "article_patterns": (),
    },
    {
        "name": "Mais Goiás",
        "feed_urls": ("https://www.maisgoias.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("maisgoias.com.br",),
        "article_patterns": (),
    },
    {
        "name": "Dia Online",
        "feed_urls": ("https://diaonline.ig.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("diaonline.ig.com.br",),
        "article_patterns": (),
    },
    {
        "name": "Sagres Online",
        "feed_urls": ("https://sagresonline.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("sagresonline.com.br",),
        "article_patterns": (),
    },
    {
        "name": "Folha Z",
        "feed_urls": ("https://folhaz.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("folhaz.com.br",),
        "article_patterns": (),
    },
    {
        "name": "Oeste Goiano",
        "feed_urls": ("https://oestegoiano.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("oestegoiano.com.br",),
        "article_patterns": (),
    },
    {
        "name": "Tribuna do Planalto",
        "feed_urls": ("https://tribunadoplanalto.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("tribunadoplanalto.com.br",),
        "article_patterns": (),
    },
    {
        "name": "Zap Catalão",
        "feed_urls": ("https://www.zapcatalao.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("zapcatalao.com.br",),
        "article_patterns": (),
    },
    {
        "name": "Revista Bula",
        "feed_urls": ("https://www.revistabula.com/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("revistabula.com",),
        "article_patterns": (),
    },
    {
        "name": "Agência Goiás de Notícias",
        "feed_urls": ("https://goias.gov.br/categoria/noticias/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("goias.gov.br",),
        "article_patterns": (),
    },
    {
        "name": "Jornal Visão",
        "feed_urls": ("https://jornalvisao.com.br/feed/",),
        "listing_urls": (),
        "allowed_hosts": ("jornalvisao.com.br",),
        "article_patterns": (),
    },
    {
        "name": "O Popular",
        "feed_urls": (),
        "listing_urls": (
            "https://opopular.com.br/ultimas",
            "https://opopular.com.br/politica",
            "https://opopular.com.br/cidades",
            "https://opopular.com.br/economia",
        ),
        "allowed_hosts": ("opopular.com.br",),
        "article_patterns": (r"^/.+?/.+-\d+\.\d+$",),
    },
)
_LOCAL_PORTAL_HOSTS = {
    host
    for source in _LOCAL_PORTAL_SOURCES
    for host in source["allowed_hosts"]
}
_LOCAL_PORTAL_BLOCKED_PATH_TOKENS = (
    "/anuncie",
    "/autor",
    "/author",
    "/categoria",
    "/contato",
    "/expediente",
    "/feed",
    "/fale-conosco",
    "/politica-de-privacidade",
    "/termos",
)


class _AnchorTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_text_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = ""
        for attr_name, attr_value in attrs:
            if attr_name.lower() == "href" and attr_value:
                href = attr_value.strip()
                break
        if not href:
            return
        self._current_href = href
        self._current_text_chunks = []

    def handle_data(self, data: str) -> None:
        if self._current_href is None or not data:
            return
        self._current_text_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_href is None:
            return
        text = _sanitize_title(" ".join(self._current_text_chunks))
        if text:
            self.links.append((self._current_href, text))
        self._current_href = None
        self._current_text_chunks = []


def _make_result(
    url: str,
    title: str,
    description: str = "",
    published_at: datetime | None = None,
    source_type: str = "",
) -> SearchResult:
    cleaned_title = _sanitize_title(title)
    return SearchResult(url=url, title=cleaned_title, description=description, published_at=published_at, source_type=source_type)


def _normalize_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().strip()
    if host.startswith("www."):
        return host[4:]
    return host


def _unwrap_google_redirect_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""

    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host != "google.com" or parsed.path != "/url":
        return value

    query = parse_qs(parsed.query)
    for key in ("url", "q"):
        candidate = (query.get(key) or [""])[0].strip()
        candidate_parsed = urlparse(candidate)
        if candidate_parsed.scheme in {"http", "https"} and candidate_parsed.netloc:
            return candidate

    return value


def is_local_portal_url(url: str) -> bool:
    return _normalize_host(url) in _LOCAL_PORTAL_HOSTS


def _sanitize_title(value: str) -> str:
    cleaned = unescape(value or "")
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _rss_entry_published_at(entry: dict) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is not None:
        try:
            return datetime(*parsed[:6])
        except Exception:
            pass

    text_value = (entry.get("published") or entry.get("updated") or "").strip()
    if not text_value:
        return None
    try:
        dt = parsedate_to_datetime(text_value)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _normalize_text(value: str) -> str:
    text = unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_candidate_text(
    value: str,
    max_sentences: int | None = 3,
    max_chars: int | None = 420,
) -> str:
    text = unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    marker_match = _RELATED_CONTENT_SPLIT_RE.search(text)
    if marker_match:
        text = text[:marker_match.start()].strip(" -:|\t\n\r")

    if not text:
        return ""

    sentences = [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]
    if sentences and max_sentences is not None:
        text = " ".join(sentences[:max_sentences])

    if max_chars is not None:
        text = text[:max_chars]

    return text.strip()


def _build_entity_variations(entity_terms: List[str] | None) -> List[str]:
    raw_terms = [term for term in (entity_terms or []) if term and term.strip()]
    variations: list[str] = []
    seen: set[str] = set()

    for term in raw_terms:
        normalized = _normalize_text(term)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        variations.append(normalized)

        compact = normalized.replace(" ", "")
        if compact and compact not in seen:
            seen.add(compact)
            variations.append(compact)

    variations.sort(key=len, reverse=True)
    return variations


def _has_goias_context(text: str) -> bool:
    hay = _normalize_text(text)
    if not hay:
        return False
    compact_hay = hay.replace(" ", "")
    for marker in _GOIAS_CONTEXT_MARKERS:
        normalized_marker = _normalize_text(marker)
        if not normalized_marker:
            continue
        if normalized_marker in hay:
            return True
        if normalized_marker.replace(" ", "") in compact_hay:
            return True
    return False


def _matches_entity_variations(text: str, variations: List[str]) -> bool:
    hay = _normalize_text(text)
    if not hay or not variations:
        return False

    hay_tokens = set(hay.split())
    compact_hay = hay.replace(" ", "")

    for variation in variations:
        if not variation:
            continue
        if variation in hay:
            return True

        compact_variation = variation.replace(" ", "")
        if compact_variation and compact_variation in compact_hay:
            return True

        var_tokens = [
            token for token in variation.split()
            if token not in _TERM_STOPWORDS and token not in _WEAK_MATCH_TOKENS and len(token) > 2
        ]
        if len(var_tokens) < 2:
            continue

        overlap = sum(1 for token in var_tokens if token in hay_tokens)
        if overlap >= min(2, len(var_tokens)):
            return True

    return False


def is_relevant_for_goias_entity(
    title: str,
    summary: str,
    full_text: str,
    entity_terms: List[str] | None,
) -> bool:
    """Strict relevance check for Goiás entities using full article context.

    A candidate is considered relevant only when:
    - the combined context contains Goiás markers; and
    - at least one strong variation of the entity name/keywords appears in context.
    """
    variations = _build_entity_variations(entity_terms)
    context_blob = "\n".join(part for part in [title, summary, full_text] if part)
    if not context_blob:
        return False
    if not _has_goias_context(context_blob):
        return False
    if not _matches_entity_variations(context_blob, variations):
        return False
    return True


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


def _is_scrapable_local_article(url: str, source: dict) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if _normalize_host(url) not in source["allowed_hosts"]:
        return False

    path = (parsed.path or "").strip().rstrip("/")
    lower_path = path.lower()
    if not lower_path or lower_path == "/":
        return False

    if any(token in lower_path for token in _LOCAL_PORTAL_BLOCKED_PATH_TOKENS):
        return False
    if lower_path.endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".xml", ".pdf")):
        return False

    listing_paths = {
        urlparse(listing_url).path.rstrip("/").lower()
        for listing_url in source.get("listing_urls", ())
    }
    if lower_path in listing_paths:
        return False

    for pattern in source.get("article_patterns", ()): 
        if re.search(pattern, lower_path):
            return True
    return False


def _scrape_local_listing_entries(
    source: dict,
    filter_terms: List[str],
    limit: int,
) -> List[SearchResult]:
    results: List[SearchResult] = []
    seen: set[str] = set()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
    }

    for listing_url in source.get("listing_urls", ()):
        try:
            response = requests.get(listing_url, headers=headers, timeout=20)
            response.raise_for_status()
        except Exception:
            continue

        parser = _AnchorTextExtractor()
        parser.feed(response.text[:400000])
        for href, anchor_text in parser.links:
            absolute_url = urljoin(listing_url, href)
            normalized_url = absolute_url.strip()
            if not normalized_url or normalized_url in seen:
                continue
            if not _is_scrapable_local_article(normalized_url, source):
                continue

            title = _sanitize_title(anchor_text)
            if len(title) < 12:
                continue
            if not _matches_filter_terms(title, "", filter_terms):
                continue

            seen.add(normalized_url)
            results.append(_make_result(normalized_url, title, source_type="local_portal"))
            if len(results) >= limit:
                return results
        time.sleep(0.2)

    return results


def _collect_local_portal_entries(
    filter_terms: List[str],
    tag_terms: List[str],
    strict_entity_terms: List[str],
    limit: int,
) -> List[SearchResult]:
    source_groups: list[List[SearchResult]] = []
    per_source_limit = max(1, min(3, limit))

    for source in _LOCAL_PORTAL_SOURCES:
        source_results = fetch_rss_entries(
            list(source.get("feed_urls", ())),
            filter_terms=filter_terms,
            tag_terms=tag_terms,
            strict_entity_terms=strict_entity_terms,
            require_goias_context=True,
            limit=per_source_limit,
            source_type="local_portal",
        )
        if len(source_results) < min(2, per_source_limit) and source.get("listing_urls"):
            scraped_results = _scrape_local_listing_entries(source, filter_terms, per_source_limit)
            source_results = _merge_unique_results(source_results, scraped_results, limit=per_source_limit)

        if source_results:
            source_groups.append(source_results)

    return _merge_unique_results_round_robin(*source_groups, limit=limit)


def _hydrate_candidate_hits(
    results: List[SearchResult],
    strict_entity_terms: List[str],
    limit: int,
) -> List[SearchResult]:
    hydrated_hits: List[SearchResult] = []

    for item in results:
        article_text = item.markdown or extract_article_text(item.url, summary_mode=False) or ""
        summary = _clean_candidate_text(article_text or item.description or item.title, max_sentences=3, max_chars=700)
        if article_text:
            item.markdown = article_text
        item.description = summary or _clean_candidate_text(item.description, max_sentences=3, max_chars=600)

        relevance_blob = article_text or item.description or item.title
        if not is_relevant_for_goias_entity(item.title, item.description, relevance_blob, strict_entity_terms):
            continue

        hydrated_hits.append(item)
        if len(hydrated_hits) >= limit:
            break

    return hydrated_hits


def fetch_rss_entries(
    feed_urls: List[str],
    filter_terms: List[str] | None = None,
    limit: int = 10,
    tag_terms: List[str] | None = None,
    strict_entity_terms: List[str] | None = None,
    require_goias_context: bool = False,
    source_type: str = "",
) -> List[SearchResult]:
    """Fetch and filter entries from a list of RSS/Atom URLs.

    filter_terms: if provided, only return entries where any term appears in title/summary.
    """
    results: List[SearchResult] = []
    seen: set[str] = set()
    terms = [t.lower() for t in (filter_terms or [])]
    strict_variations = _build_entity_variations(strict_entity_terms)

    for feed_url in feed_urls or []:
        try:
            parsed = feedparser.parse(feed_url)
        except Exception:
            continue

        entries = getattr(parsed, "entries", []) or []
        for e in entries:
            link = _unwrap_google_redirect_url((e.get("link") or "").strip())
            if not link or link in seen:
                continue
            title = _sanitize_title((e.get("title") or "").strip())
            summary = _clean_candidate_text((e.get("summary") or e.get("description") or "").strip())
            if tag_terms is not None and not _matches_entity_tags(title, summary, tag_terms):
                continue
            if not _matches_filter_terms(title, summary, terms):
                continue

            full_text = ""
            context_blob = "\n".join(part for part in [title, summary] if part)
            if strict_variations or require_goias_context:
                # Fast-path using title/summary first to avoid expensive extraction on obvious misses.
                if require_goias_context and not _has_goias_context(context_blob):
                    continue
                if strict_variations and not _matches_entity_variations(context_blob, strict_variations):
                    continue

            if full_text:
                summary = _clean_candidate_text(full_text, max_sentences=3, max_chars=700)

            seen.add(link)
            item = _make_result(link, title or link, summary, published_at=_rss_entry_published_at(e), source_type=source_type)
            if full_text:
                item.markdown = full_text
            results.append(item)
            if len(results) >= limit:
                return results
        # be polite between feed calls
        time.sleep(0.2)

    return results


def extract_article_text(url: str, summary_mode: bool = True) -> str | None:
    """Extract article body using robust capture chain with local fallback."""
    details = extract_article_details(url, summary_mode=summary_mode)
    return details[0]


def extract_article_details(url: str, summary_mode: bool = True) -> tuple[str | None, datetime | None]:
    """Extract article body and publication date using robust capture chain."""
    try:
        captured_details = google_search.capture_article_details(url, summary_mode=summary_mode)
    except Exception:
        captured_details = google_search.CapturedArticle(text=None, published_at=None)
    if captured_details.text:
        return captured_details.text, captured_details.published_at

    if trafilatura is None:
        return None, captured_details.published_at
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None, captured_details.published_at
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        if summary_mode:
            cleaned = _clean_candidate_text(text or "", max_sentences=6, max_chars=1800)
        else:
            cleaned = _clean_candidate_text(text or "", max_sentences=None, max_chars=120000)
        return cleaned or None, captured_details.published_at
    except Exception:
        return None, captured_details.published_at


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


def _merge_unique_results_round_robin(*groups: List[SearchResult], limit: int) -> List[SearchResult]:
    results: List[SearchResult] = []
    seen: set[str] = set()
    group_lists = [group for group in groups if group]
    indexes = [0] * len(group_lists)

    while len(results) < limit and group_lists:
        progressed = False
        for group_index, group in enumerate(group_lists):
            while indexes[group_index] < len(group):
                item = group[indexes[group_index]]
                indexes[group_index] += 1
                if not item.url or item.url in seen:
                    continue
                seen.add(item.url)
                results.append(item)
                progressed = True
                break
            if len(results) >= limit:
                return results
        if not progressed:
            break

    return results


def _entity_terms(entity: dict) -> tuple[str, list[str], list[str], list[str]]:
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
    strict_entity_terms = terms[:]
    tag_terms = keywords if keywords else ([name] if name else [])
    return name, keywords, terms, strict_entity_terms if strict_entity_terms else tag_terms


def collect_local_portals_for_entity(entity: dict, max_results: int = 8) -> List[SearchResult]:
    """Collect local Goiás portal candidates for an entity.

    This is the primary and mandatory capture source in the news pipeline.
    """
    _name, _keywords, terms, strict_entity_terms = _entity_terms(entity)
    if not terms:
        return []

    local_portal_hits = _collect_local_portal_entries(
        filter_terms=terms,
        tag_terms=terms,
        strict_entity_terms=strict_entity_terms,
        limit=max_results,
    )
    if not local_portal_hits:
        return []
    return _hydrate_candidate_hits(local_portal_hits, strict_entity_terms, max_results)


def collect_alerts_and_feeds_for_entity(entity: dict, max_results: int = 8) -> List[SearchResult]:
    """Collect entity/global alerts and manual RSS feeds as complementary sources."""
    name, _keywords, terms, strict_entity_terms = _entity_terms(entity)
    if not terms:
        return []

    entity_google_alert_feed = (entity.get("google_alert_rss_url") or "").strip()
    entity_google_alert_feeds = [entity_google_alert_feed] if entity_google_alert_feed else []

    # Google Alerts are validated using entity tags first.
    tag_terms = terms if terms else [name]
    entity_ga_hits = fetch_rss_entries(
        entity_google_alert_feeds,
        filter_terms=terms,
        tag_terms=tag_terms,
        strict_entity_terms=strict_entity_terms,
        require_goias_context=True,
        limit=max_results,
        source_type="google_alert_entity",
    )
    ga_hits = fetch_rss_entries(
        GOOGLE_ALERTS_RSS,
        filter_terms=terms,
        tag_terms=tag_terms,
        strict_entity_terms=strict_entity_terms,
        require_goias_context=True,
        limit=max_results,
        source_type="google_alert_global",
    )
    rss_hits = fetch_rss_entries(
        RSS_FEEDS,
        filter_terms=terms,
        tag_terms=tag_terms,
        strict_entity_terms=strict_entity_terms,
        require_goias_context=True,
        limit=max_results,
        source_type="rss_manual",
    )

    merged_hits = _merge_unique_results_round_robin(
        entity_ga_hits,
        ga_hits,
        rss_hits,
        limit=max_results,
    )
    if merged_hits:
        return _hydrate_candidate_hits(merged_hits, strict_entity_terms, max_results)

    return []


def collect_for_entity(entity: dict, max_results: int = 8) -> List[SearchResult]:
    """Backward-compatible aggregate collector.

    Preferred usage in orchestrators:
    1) collect_local_portals_for_entity (mandatory)
    2) collect_alerts_and_feeds_for_entity (complementary)
    """
    _name, _keywords, terms, strict_entity_terms = _entity_terms(entity)
    if not terms:
        return []

    local_hits = collect_local_portals_for_entity(entity, max_results=max_results)
    complementary_hits = collect_alerts_and_feeds_for_entity(entity, max_results=max_results)
    merged_hits = _merge_unique_results_round_robin(local_hits, complementary_hits, limit=max_results)
    if merged_hits:
        return _hydrate_candidate_hits(merged_hits, strict_entity_terms, max_results)

    return []
