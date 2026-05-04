"""Utilities for deduplicating news records before persistence."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from db import query_one

_TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
    "ref",
    "ref_src",
    "utm_campaign",
    "utm_content",
    "utm_id",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def normalize_text(value: str | None, max_chars: int = 4000) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:max_chars]


def normalize_url(url: str | None) -> str:
    if not url:
        return ""
    value = url.strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if not parsed.netloc:
        return value.lower()

    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path or "/"
    path = re.sub(r"/+", "/", path)
    if path.endswith("/") and path != "/":
        path = path[:-1]
    if path.endswith(".amp"):
        path = path[:-4]
    if path.endswith(".amp.html"):
        path = path[:-9] + ".html"

    query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
    cleaned_query_pairs = [
        (k, v)
        for (k, v) in query_pairs
        if k.lower() not in _TRACKING_QUERY_PARAMS and not k.lower().startswith("utm_")
    ]
    cleaned_query_pairs.sort(key=lambda item: (item[0], item[1]))
    cleaned_query = urlencode(cleaned_query_pairs, doseq=True)

    return urlunparse((scheme, netloc, path, "", cleaned_query, ""))


def build_dedup_fields(
    *,
    title: str | None,
    content: str | None,
    full_text: str | None,
    source_url: str | None,
) -> dict[str, str]:
    source_url_norm = normalize_url(source_url)
    title_norm = normalize_text(title, max_chars=600)
    content_norm = normalize_text(full_text or content, max_chars=8000)
    content_hash = hashlib.sha256(content_norm.encode("utf-8")).hexdigest() if content_norm else ""

    dedup_basis = f"{title_norm}|{content_hash}" if (title_norm or content_hash) else ""
    dedup_key = hashlib.sha256(dedup_basis.encode("utf-8")).hexdigest() if dedup_basis else ""

    return {
        "source_url_norm": source_url_norm,
        "title_norm": title_norm,
        "content_hash": content_hash,
        "dedup_key": dedup_key,
    }


def find_existing_news_duplicate(
    *,
    source_url: str,
    source_url_norm: str,
    title_norm: str,
    content_hash: str,
    dedup_key: str,
) -> str | None:
    row = query_one(
        """
        SELECT id
        FROM news_items
          WHERE (%s <> '' AND source_url = %s)
              OR (%s <> '' AND source_url_norm = %s)
              OR (%s <> '' AND dedup_key = %s)
              OR (%s <> '' AND %s <> '' AND title_norm = %s AND content_hash = %s)
        LIMIT 1
        """,
        (
                source_url,
                source_url,
            source_url_norm,
            source_url_norm,
            dedup_key,
            dedup_key,
            title_norm,
            content_hash,
            title_norm,
            content_hash,
        ),
    )
    return str(row["id"]) if row and row.get("id") else None
