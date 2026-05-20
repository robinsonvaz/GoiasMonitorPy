"""Sanitize persisted news titles by reconciling them with source page titles.

Default mode is DRY-RUN. Use --apply to persist updates.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from difflib import SequenceMatcher
from html import unescape
import re
import time
from typing import Any
from urllib.parse import urlparse

import requests

from db import execute_many, query_all
from tools.news_dedup import normalize_text


_TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", flags=re.IGNORECASE | re.DOTALL)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", flags=re.IGNORECASE | re.DOTALL)
_META_TEMPLATE = r'<meta[^>]+(?:property|name)=["\']{key}["\'][^>]+content=["\']([^"\']+)["\']'
_TAG_RE = re.compile(r"<[^>]+>")
_COMMON_SITE_TOKENS = {
    "com",
    "br",
    "org",
    "net",
    "news",
    "portal",
    "site",
    "blog",
}


@dataclass
class TitleCapture:
    title: str | None
    source_kind: str
    final_url: str
    status: str


@dataclass
class Decision:
    should_update: bool
    reason: str
    similarity: float


def _clean_text(value: str) -> str:
    cleaned = _TAG_RE.sub(" ", value or "")
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\n\r-|")
    return cleaned


def _meta_content(html: str, key: str) -> str | None:
    pattern = re.compile(_META_TEMPLATE.format(key=re.escape(key)), flags=re.IGNORECASE)
    match = pattern.search(html)
    if not match:
        return None
    return _clean_text(match.group(1))


def _hostname_tokens(url: str) -> set[str]:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    tokens = set(re.findall(r"[a-z0-9]+", host))
    return {tok for tok in tokens if tok and tok not in _COMMON_SITE_TOKENS}


def _strip_title_suffix(title: str, final_url: str) -> str:
    separators = (" | ", " - ", " — ", " :: ")
    current = title
    host_tokens = _hostname_tokens(final_url)

    for sep in separators:
        if sep not in current:
            continue
        parts = [part.strip() for part in current.split(sep) if part.strip()]
        if len(parts) < 2:
            continue
        head = sep.join(parts[:-1]).strip()
        tail = parts[-1]
        tail_tokens = set(re.findall(r"[a-z0-9]+", normalize_text(tail, max_chars=200)))
        tail_tokens = {tok for tok in tail_tokens if tok not in _COMMON_SITE_TOKENS}

        # Remove common site suffix from fallback <title> captures.
        if head and tail and (
            (host_tokens and tail_tokens and bool(host_tokens & tail_tokens))
            or (len(head) >= 35 and len(tail) <= 28)
        ):
            current = head
            break

    return current.strip()


def _capture_source_title(url: str, timeout: int) -> TitleCapture:
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
            },
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.RequestException:
        return TitleCapture(title=None, source_kind="request", final_url=url, status="request_error")

    final_url = str(response.url or url)
    if not response.ok:
        return TitleCapture(title=None, source_kind="http", final_url=final_url, status=f"http_{response.status_code}")

    html = response.text[:400000]
    if not html:
        return TitleCapture(title=None, source_kind="html", final_url=final_url, status="empty_html")

    for key, source_kind in (
        ("og:title", "og:title"),
        ("twitter:title", "twitter:title"),
    ):
        value = _meta_content(html, key)
        if value:
            return TitleCapture(title=value, source_kind=source_kind, final_url=final_url, status="ok")

    title_match = _TITLE_TAG_RE.search(html)
    if title_match:
        value = _clean_text(title_match.group(1))
        if value:
            return TitleCapture(
                title=_strip_title_suffix(value, final_url),
                source_kind="title_tag",
                final_url=final_url,
                status="ok",
            )

    h1_match = _H1_RE.search(html)
    if h1_match:
        value = _clean_text(h1_match.group(1))
        if value:
            return TitleCapture(title=value, source_kind="h1", final_url=final_url, status="ok")

    return TitleCapture(title=None, source_kind="parse", final_url=final_url, status="title_not_found")


def _token_set(value: str) -> set[str]:
    normalized = normalize_text(value, max_chars=600)
    tokens = set(re.findall(r"[a-z0-9]{3,}", normalized))
    return {
        tok
        for tok in tokens
        if tok not in {"com", "br", "www", "http", "https", "noticia", "noticias"}
    }


def _contains_goias(value: str) -> bool:
    n = normalize_text(value, max_chars=600)
    return "goias" in n or "goias" in n.replace(" ", "")


def _should_update_title(current_title: str, captured_title: str, source_kind: str) -> Decision:
    current_norm = normalize_text(current_title, max_chars=600)
    captured_norm = normalize_text(captured_title, max_chars=600)

    if not captured_norm:
        return Decision(False, "captured_empty", 1.0)
    if current_norm == captured_norm:
        return Decision(False, "already_equal", 1.0)

    similarity = SequenceMatcher(None, current_norm, captured_norm).ratio()
    token_diff = len(_token_set(current_norm) ^ _token_set(captured_norm))

    # Strong signal for the specific bug pattern: geography injected by rewrite.
    if _contains_goias(current_title) and not _contains_goias(captured_title):
        return Decision(True, "goias_injected", similarity)

    if source_kind in {"og:title", "twitter:title"}:
        if similarity < 0.97 or token_diff >= 2:
            return Decision(True, "high_confidence_title_diff", similarity)
        return Decision(False, "minor_high_confidence_diff", similarity)

    # Lower confidence fallback from <title> or <h1> should be stricter.
    if similarity < 0.90 or token_diff >= 3:
        return Decision(True, "fallback_title_diff", similarity)
    return Decision(False, "minor_fallback_diff", similarity)


def _load_candidates(news_id: str | None, limit: int | None) -> list[dict[str, Any]]:
    sql = """
        SELECT id, title, source_url, collected_at
        FROM news_items
        WHERE source_url IS NOT NULL
          AND source_url <> ''
          AND title IS NOT NULL
          AND title <> ''
    """
    params: list[Any] = []

    if news_id:
        sql += " AND id = %s"
        params.append(news_id)

    sql += " ORDER BY collected_at DESC"
    if limit is not None and limit > 0:
        sql += " LIMIT %s"
        params.append(limit)

    rows = query_all(sql, tuple(params) if params else None)
    return list(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Saneia titulos de noticias comparando com titulo real da pagina de origem."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica updates no banco. Sem a flag, executa em dry-run.",
    )
    parser.add_argument(
        "--news-id",
        default="",
        help="Processa apenas uma noticia especifica (UUID).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limita a quantidade de noticias analisadas (0 = sem limite).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="Timeout (segundos) por requisicao HTTP para captura do titulo.",
    )
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=300,
        help="Pausa entre capturas (ms) para reduzir carga e bloqueios.",
    )
    parser.add_argument(
        "--print-updates",
        action="store_true",
        help="Exibe detalhes dos titulos candidatos a atualizacao.",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    only_id = args.news_id.strip() or None
    limit = args.limit if args.limit > 0 else None
    sleep_seconds = max(0, args.sleep_ms) / 1000.0

    rows = _load_candidates(news_id=only_id, limit=limit)
    if not rows:
        print("Nenhuma noticia encontrada para saneamento de titulo.")
        return

    checked = 0
    captures_ok = 0
    fetch_failures = 0
    parse_failures = 0
    unchanged = 0
    candidates = 0

    updates: list[tuple[str, str, str]] = []

    for row in rows:
        checked += 1
        news_id = str(row["id"])
        current_title = (row.get("title") or "").strip()
        source_url = (row.get("source_url") or "").strip()

        if not source_url:
            unchanged += 1
            continue

        captured = _capture_source_title(source_url, timeout=max(5, args.timeout))
        if captured.status != "ok":
            if captured.status == "title_not_found":
                parse_failures += 1
            else:
                fetch_failures += 1
            continue

        captures_ok += 1
        captured_title = (captured.title or "").strip()
        if len(captured_title) < 8:
            parse_failures += 1
            continue

        decision = _should_update_title(current_title, captured_title, captured.source_kind)
        if not decision.should_update:
            unchanged += 1
            continue

        candidates += 1
        updates.append((captured_title, normalize_text(captured_title, max_chars=600), news_id))

        if args.print_updates:
            print(
                f"[UPDATE] id={news_id} reason={decision.reason} sim={decision.similarity:.3f} "
                f"source={captured.source_kind}\n"
                f"  old: {current_title[:220]}\n"
                f"  new: {captured_title[:220]}"
            )

        if sleep_seconds:
            time.sleep(sleep_seconds)

    updated_rows = 0
    if updates and not dry_run:
        updated_rows = execute_many(
            """
            UPDATE news_items
            SET title = %s,
                title_norm = %s
            WHERE id = %s
            """,
            updates,
        )

    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"Modo: {mode}")
    print(f"Analisadas: {checked}")
    print(f"Capturas ok: {captures_ok}")
    print(f"Falhas HTTP/requisicao: {fetch_failures}")
    print(f"Falhas de parse de titulo: {parse_failures}")
    print(f"Sem alteracao: {unchanged}")
    print(f"Candidatas a update: {candidates}")
    print(f"Atualizadas no banco: {updated_rows}")


if __name__ == "__main__":
    main()
