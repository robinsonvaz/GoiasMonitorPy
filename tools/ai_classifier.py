"""AI classification tool — uses Lovable AI Gateway (OpenAI-compatible)."""
from __future__ import annotations
import json
import re
import requests
from config import LOVABLE_API_KEY


def classify_news(text_content: str, title: str, url: str, entity_name: str) -> dict | None:
    """Classify a news article for an entity using the AI gateway.

    Returns a dict with keys: title, content, sentiment, classification,
    people_mentioned, relevant — or None on failure.
    """
    truncated = text_content[:3000]

    with open("prompts/news_classifier.txt", encoding="utf-8") as f:
        system_prompt = f.read().replace("{{entity_name}}", entity_name)

    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Título: {title}\nURL: {url}\nConteúdo:\n{truncated}",
            },
        ],
        "temperature": 0.1,
    }

    response = requests.post(
        "https://ai.gateway.lovable.dev/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {LOVABLE_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if not response.ok:
        return None

    raw = response.json()
    content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
    cleaned = re.sub(r"```json\n?|```\n?", "", content).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None
