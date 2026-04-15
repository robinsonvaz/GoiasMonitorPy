"""Firecrawl search tool — searches the web via Firecrawl API."""
from __future__ import annotations
from dataclasses import dataclass
import requests


@dataclass
class SearchResult:
    url: str
    title: str
    description: str = ""
    markdown: str = ""


def search(api_key: str, query: str, limit: int = 5) -> tuple[list[SearchResult], bool]:
    """Search via Firecrawl.

    Returns (results, credits_exhausted).
    """
    response = requests.post(
        "https://api.firecrawl.dev/v1/search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "limit": limit,
            "lang": "pt-br",
            "country": "br",
            "tbs": "qdr:w",
            "scrapeOptions": {"formats": ["markdown"]},
        },
        timeout=30,
    )

    data = response.json()

    if not response.ok:
        if response.status_code == 402 or "Insufficient credits" in str(data.get("error", "")):
            return [], True
        raise RuntimeError(f"Firecrawl error: {data}")

    raw = data.get("data") or []
    results = [
        SearchResult(
            url=r.get("url", ""),
            title=r.get("title", ""),
            description=r.get("description", ""),
            markdown=r.get("markdown", ""),
        )
        for r in raw
        if r.get("url")
    ]
    return results, False
