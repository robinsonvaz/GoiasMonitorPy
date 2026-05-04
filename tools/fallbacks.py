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


def fetch_rss_entries(
    feed_urls: List[str],
    filter_terms: List[str] | None = None,
    limit: int = 10,
    tag_terms: List[str] | None = None,
    strict_entity_terms: List[str] | None = None,
    require_goias_context: bool = False,
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
            link = (e.get("link") or "").strip()
            if not link or link in seen:
                continue
            title = (e.get("title") or "").strip()
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
            item = _make_result(link, title or link, summary)
            if full_text:
                item.markdown = full_text
            results.append(item)
            if len(results) >= limit:
                return results
        # be polite between feed calls
        time.sleep(0.2)

    return results


def extract_article_text(url: str, summary_mode: bool = True) -> str | None:
    """Attempt to extract article body using trafilatura when available."""
    if trafilatura is None:
        return None
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        if summary_mode:
            cleaned = _clean_candidate_text(text or "", max_sentences=6, max_chars=1800)
        else:
            cleaned = _clean_candidate_text(text or "", max_sentences=None, max_chars=120000)
        return cleaned or None
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
    strict_entity_terms = terms[:]

    entity_google_alert_feed = (entity.get("google_alert_rss_url") or "").strip()
    entity_google_alert_feeds = [entity_google_alert_feed] if entity_google_alert_feed else []

    # 1) Google Alerts are validated using entity tags (keywords) first.
    tag_terms = keywords if keywords else [name]
    entity_ga_hits = fetch_rss_entries(
        entity_google_alert_feeds,
        filter_terms=terms,
        tag_terms=tag_terms,
        strict_entity_terms=strict_entity_terms,
        require_goias_context=True,
        limit=max_results,
    )
    ga_hits = fetch_rss_entries(
        GOOGLE_ALERTS_RSS,
        filter_terms=terms,
        tag_terms=tag_terms,
        strict_entity_terms=strict_entity_terms,
        require_goias_context=True,
        limit=max_results,
    )
    rss_hits = fetch_rss_entries(
        RSS_FEEDS,
        filter_terms=terms,
        tag_terms=tag_terms,
        strict_entity_terms=strict_entity_terms,
        require_goias_context=True,
        limit=max_results,
    )
    merged_hits = _merge_unique_results(entity_ga_hits, ga_hits, rss_hits, limit=max_results)
    if merged_hits:
        for item in merged_hits:
            article_text = item.markdown or extract_article_text(item.url, summary_mode=False)
            if article_text:
                item.markdown = article_text
                item.description = _clean_candidate_text(article_text, max_sentences=3, max_chars=700)
            else:
                item.description = _clean_candidate_text(item.description, max_sentences=3, max_chars=600)
        return merged_hits

    # 3) Nothing found here — return empty list so caller can run search fallbacks
    return []
