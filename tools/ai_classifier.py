"""AI classification tool — uses Lovable AI Gateway (OpenAI-compatible)."""
from __future__ import annotations

import json
import re
from typing import Any

import requests

from config import LOVABLE_API_KEY


_ORG_PREFIX_RE = re.compile(
    r"^(secretaria|minist[eé]rio|prefeitura|munic[ií]pio|tribunal|assembleia|c[aâ]mara|hospital|sociedade|sindsa[uú]de)\b",
    re.IGNORECASE,
)


def _is_org_like(value: str) -> bool:
    normalized = value.casefold()
    keywords = (
        "secretaria", "ministério", "ministerio", "prefeitura", "município", "municipio",
        "tribunal", "assembleia", "câmara", "camara", "hospital", "sociedade",
        "sindsaúde", "sindsaude", "banco", "cooperativa", "grupo", "ltda", "s/a",
        "s.a", "eireli", "mei", "epp", "fieg", "acieg", "saneago", "comurg",
        "codego", "goiasfomento", "celg", "sicredi", "sicoob", "equatorial",
    )
    return any(keyword in normalized for keyword in keywords)


def _format_org_mention(value: str) -> str:
    lowercase_words = {"de", "da", "do", "das", "dos", "e", "em", "para"}
    words = value.split()
    formatted: list[str] = []
    for index, word in enumerate(words):
        if any(char.isupper() for char in word[1:]) or "/" in word or "-" in word and word.upper() == word:
            formatted.append(word)
            continue
        lowered = word.casefold()
        if index > 0 and lowered in lowercase_words:
            formatted.append(lowered)
        else:
            formatted.append(lowered[:1].upper() + lowered[1:])
    return " ".join(formatted)


def _meaningful_tokens(value: str) -> set[str]:
    stopwords = {"de", "da", "do", "das", "dos", "e", "em", "para", "goias", "goiás", "estado"}
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", value.casefold())
    return {token for token in tokens if token not in stopwords}


def _clean_org_mention(value: str) -> list[str]:
    mention = _normalize_mention(value)
    if not mention:
        return []

    lower = mention.casefold()
    if lower.startswith(("de ", "da ", "do ", "em ", "no ", "na ", "sobre ", "crise ")):
        return []

    mention = re.split(
        r"\s+e\s+(?:da|do|de)\s+(?=(Sociedade|Secretaria|Minist[eé]rio|Prefeitura|Munic[ií]pio|Tribunal|Assembleia|C[aâ]mara|Hospital|Sindsa[uú]de)\b)",
        mention,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    parts = re.split(
        r"\s+e\s+(?=(Secretaria|Minist[eé]rio|Prefeitura|Munic[ií]pio|Tribunal|Assembleia|C[aâ]mara|Hospital|Sociedade|Sindsa[uú]de)\b)",
        mention,
        flags=re.IGNORECASE,
    )
    if len(parts) > 1:
        combined: list[str] = []
        current = parts[0]
        combined.append(current)
        for index in range(1, len(parts), 2):
            prefix = parts[index]
            tail = parts[index + 1] if index + 1 < len(parts) else ""
            combined.append(prefix + tail)
        cleaned_parts: list[str] = []
        for item in combined:
            cleaned_parts.extend(_clean_org_mention(item))
        return cleaned_parts

    mention = re.split(
        r"\s+(?:informa|informou|afirma|afirmou|anuncia|anunciou|abrigara|abrigará|volta|voltou|troca|deixa|deixou|promove|promoveu|sera|será|foi|apos|após|para|sobre|celebraram?|expressa|emite|emitiu)\b",
        mention,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    mention = re.sub(r"\s+e\s+outras\b.*$", "", mention, flags=re.IGNORECASE)
    mention = re.sub(r"\s+o\s+sindsa[uú]de\b.*$", "", mention, flags=re.IGNORECASE)
    mention = re.sub(r"\s+a\s+secretaria\b.*$", "", mention, flags=re.IGNORECASE)
    mention = _normalize_mention(mention)

    canonical_patterns = [
        r"Secretaria\s+(?:de|da|do)\s+[A-Za-zÀ-ÖØ-öø-ÿ]+(?:\s+(?:de|da|do|dos|das)\s+[A-Za-zÀ-ÖØ-öø-ÿ]+){0,6}",
        r"Minist[eé]rio\s+(?:de|da|do)\s+[A-Za-zÀ-ÖØ-öø-ÿ]+(?:\s+(?:de|da|do|dos|das)\s+[A-Za-zÀ-ÖØ-öø-ÿ]+){0,6}",
        r"Prefeitura\s+(?:de|da|do)\s+[A-Za-zÀ-ÖØ-öø-ÿ]+(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ]+){0,4}",
        r"Munic[ií]pio\s+(?:de|da|do)\s+[A-Za-zÀ-ÖØ-öø-ÿ]+(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ]+){0,4}",
        r"Tribunal\s+(?:de|da|do)\s+[A-Za-zÀ-ÖØ-öø-ÿ]+(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ]+){0,6}",
        r"Assembleia\s+Legislativa(?:\s+de\s+[A-Za-zÀ-ÖØ-öø-ÿ]+){0,3}",
        r"C[aâ]mara\s+Municipal(?:\s+de\s+[A-Za-zÀ-ÖØ-öø-ÿ]+){0,4}",
        r"Hospital(?:\s+e\s+Maternidade)?\s+[A-Za-zÀ-ÖØ-öø-ÿ]+(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ]+){0,6}",
        r"Sociedade\s+Beneficente\s+[A-Za-zÀ-ÖØ-öø-ÿ]+(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ]+){0,4}",
        r"Sindsa[uú]de(?:\/[A-Za-zÀ-ÖØ-öø-ÿ-]+|\s+[A-Za-zÀ-ÖØ-öø-ÿ-]+){0,4}",
    ]
    canonical_match = False
    for pattern in canonical_patterns:
        match = re.search(pattern, mention, flags=re.IGNORECASE)
        if match:
            mention = _normalize_mention(match.group(0))
            canonical_match = True
            break

    mention = _format_org_mention(mention)

    if len(mention) < 4:
        return []
    if _is_org_like(mention) and not canonical_match and not _ORG_PREFIX_RE.match(mention):
        return []
    if mention[:1].islower() and not _ORG_PREFIX_RE.match(mention):
        return []
    return [mention]


def _compact_mentions(values: list[str]) -> list[str]:
    result: list[str] = []
    for mention in values:
        lower = mention.casefold()
        mention_tokens = _meaningful_tokens(mention)
        replaced = False
        for index, existing in enumerate(result):
            existing_lower = existing.casefold()
            existing_tokens = _meaningful_tokens(existing)
            if lower == existing_lower:
                replaced = True
                break
            if lower.startswith(existing_lower) or existing_lower.startswith(lower):
                if len(mention) > len(existing):
                    result[index] = mention
                replaced = True
                break
            if _is_org_like(mention) and _is_org_like(existing):
                if mention_tokens and existing_tokens and mention_tokens == existing_tokens:
                    if len(mention) > len(existing):
                        result[index] = mention
                    replaced = True
                    break
                if mention_tokens and mention_tokens.issubset(existing_tokens):
                    replaced = True
                    break
                if existing_tokens and existing_tokens.issubset(mention_tokens):
                    result[index] = mention
                    replaced = True
                    break
        if not replaced:
            result.append(mention)
    return result


def _normalize_mention(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" \t\n\r,.;:-")
    return cleaned


def _extract_company_mentions(text: str) -> list[str]:
    if not text:
        return []

    candidates: list[str] = []

    legal_entity_re = re.compile(
        r"\b([A-Z0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9&.,'\-/ ]{2,80}?)\s+"
        r"(LTDA\.?|S\/A|S\.A\.?|EIRELI|MEI|EPP|ME)\b",
        re.IGNORECASE,
    )
    for match in legal_entity_re.finditer(text):
        mention = _normalize_mention(match.group(0))
        if len(mention) >= 4:
            candidates.append(mention)

    org_terms = [
        "SANEAGO", "COMURG", "CODEGO", "AGEHAB", "GOIASFOMENTO", "CELG",
        "EQUATORIAL GOIAS", "FIEG", "FECOMERCIO", "ACIEG", "SICOOB", "SICREDI",
    ]
    upper_text = text.upper()
    for term in org_terms:
        if term in upper_text:
            candidates.append(term.title())

    activity_re = re.compile(
        r"\b([A-Z][A-Za-zÀ-ÖØ-öø-ÿ'\-]+(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'\-]+){0,4})\s+"
        r"(Construtora|Empreendimentos|Incorporadora|Cooperativa|Banco|Hospital|Clinica|"
        r"Laboratorio|Distribuidora|Transportes|Logistica|Energia|Saneamento)\b",
        re.IGNORECASE,
    )
    for match in activity_re.finditer(text):
        mention = _normalize_mention(match.group(0))
        if len(mention) >= 6:
            candidates.append(mention)

    institution_re = re.compile(
        r"\b(Secretaria\s+(?:de|da|do)\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ\s\-]{2,80}|"
        r"Prefeitura\s+(?:de|da|do)\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ\s\-]{2,80}|"
        r"Ministerio\s+(?:da|de|do)\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ\s\-]{2,80}|"
        r"Ministério\s+(?:da|de|do)\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ\s\-]{2,80}|"
        r"Tribunal\s+(?:de|da|do)\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ\s\-]{2,80}|"
        r"Assembleia\s+Legislativa[\s\-A-Za-zÀ-ÖØ-öø-ÿ]{0,60}|"
        r"Camara\s+Municipal[\s\-A-Za-zÀ-ÖØ-öø-ÿ]{0,60}|"
        r"Câmara\s+Municipal[\s\-A-Za-zÀ-ÖØ-öø-ÿ]{0,60}|"
        r"Hospital\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ\s\-]{2,80})\b",
        re.IGNORECASE,
    )
    for match in institution_re.finditer(text):
        mention = _normalize_mention(match.group(0))
        if len(mention) >= 8:
            candidates.append(mention)

    return candidates


def enrich_people_mentioned(
    current_mentions: list[Any] | None,
    title: str,
    content: str,
    entity_name: str = "",
) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    for value in (current_mentions or []):
        if not isinstance(value, str):
            continue
        for mention in (_clean_org_mention(value) if _is_org_like(value) else [_normalize_mention(value)]):
            if not mention:
                continue
            key = mention.casefold()
            if key not in seen:
                seen.add(key)
                merged.append(mention)

    text_blob = f"{title or ''}\n{content or ''}"
    for value in _extract_company_mentions(text_blob):
        for mention in (_clean_org_mention(value) if _is_org_like(value) else [_normalize_mention(value)]):
            if not mention:
                continue
            if entity_name and mention.casefold() == entity_name.casefold():
                continue
            key = mention.casefold()
            if key not in seen:
                seen.add(key)
                merged.append(mention)

    return _compact_mentions(merged)


def classify_news(text_content: str, title: str, url: str, entity_name: str) -> dict[str, Any] | None:
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

    raw: dict[str, Any] = response.json()
    content: str = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
    cleaned = re.sub(r"```json\n?|```\n?", "", content).strip()

    try:
        result: dict[str, Any] = json.loads(cleaned)
        base_mentions: list[Any] = []
        if isinstance(result.get("people_mentioned"), list):
            base_mentions.extend(result["people_mentioned"])

        for key in ("organizations_mentioned", "companies_mentioned", "entities_mentioned"):
            value = result.get(key)
            if isinstance(value, list):
                base_mentions.extend(value)

        result["people_mentioned"] = enrich_people_mentioned(
            base_mentions,
            title=title,
            content=truncated,
            entity_name=entity_name,
        )
        return result
    except json.JSONDecodeError:
        return None
