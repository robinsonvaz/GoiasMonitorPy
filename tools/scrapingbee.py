"""ScrapingBee Google search tool."""
from __future__ import annotations

from typing import Any

import requests

from tools.firecrawl import SearchResult


def search(api_key: str, query: str, limit: int = 5) -> list[SearchResult]:
    """Search via ScrapingBee Google API."""
    params = {
        "api_key": api_key,
        "search": query,
        "language": "pt",
        "country_code": "br",
        "nb_results": str(limit),
    }
    response = requests.get(
        "https://app.scrapingbee.com/api/v1/store/google",
        params=params,
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(f"ScrapingBee error [{response.status_code}]: {response.text}")

    data: dict[str, Any] = response.json()
    organic: list[dict[str, Any]] = data.get("organic_results") or []
    return [
        SearchResult(
            url=r.get("url", ""),
            title=r.get("title", ""),
            description=r.get("description", ""),
        )
        for r in organic
        if r.get("url")
    ]
