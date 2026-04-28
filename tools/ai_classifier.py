"""AI classification tool — uses Lovable AI Gateway (OpenAI-compatible)."""
from __future__ import annotations

import base64
import json
import re
from typing import Callable
from typing import Any

import requests

from config import (
    API_AI_GO_CONSUMER_KEY,
    API_AI_GO_CONSUMER_SECRET,
    API_AI_GO_ENDPOINT,
    API_AI_GO_MODEL,
    API_AI_GO_TOKEN_URL,
    CLAUDE_API_KEY,
    CLAUDE_MODEL,
    GOOGLE_API_KEY,
    GOOGLE_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    MISTRAL_API_KEY,
    MISTRAL_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    XAI_API_KEY,
    XAI_MODEL,
)


_ORG_PREFIX_RE = re.compile(
    r"^(secretaria|minist[eé]rio|prefeitura|munic[ií]pio|tribunal|assembleia|c[aâ]mara|hospital|sociedade|sindsa[uú]de)\b",
    re.IGNORECASE,
)
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


def _sanitize_news_text(value: str, max_chars: int = 3000) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return ""

    marker_match = _RELATED_CONTENT_SPLIT_RE.search(text)
    if marker_match:
        text = text[:marker_match.start()].strip(" -:|\t\n\r")

    return text[:max_chars].strip()


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


def _is_usable_secret(value: str) -> bool:
    secret = (value or "").strip()
    if not secret:
        return False
    lowered = secret.casefold()
    placeholders = (
        "your_",
        "change_this",
        "troque-",
        "placeholder",
        "example",
    )
    return not any(lowered.startswith(prefix) for prefix in placeholders)


def is_configured() -> bool:
    return any(
        (
            _is_usable_secret(GOOGLE_API_KEY),
            _is_usable_secret(OPENAI_API_KEY),
            _is_usable_secret(CLAUDE_API_KEY),
            _is_usable_secret(XAI_API_KEY),
            _is_usable_secret(GROQ_API_KEY),
            _is_usable_secret(MISTRAL_API_KEY),
            _is_usable_secret(API_AI_GO_CONSUMER_KEY) and _is_usable_secret(API_AI_GO_CONSUMER_SECRET),
        )
    )


def _extract_json_text(raw_text: str) -> dict[str, Any] | None:
    cleaned = re.sub(r"```json\n?|```\n?", "", raw_text or "").strip()
    if not cleaned:
        return None

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _build_user_prompt(title: str, url: str, truncated: str) -> str:
    return f"Título: {title}\nURL: {url}\nConteúdo:\n{truncated}"


def _request_google(system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
    if not _is_usable_secret(GOOGLE_API_KEY):
        return None
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GOOGLE_MODEL}:generateContent?key={GOOGLE_API_KEY}",
        headers={"Content-Type": "application/json"},
        json={
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.1},
        },
        timeout=30,
    )
    if not response.ok:
        return None
    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return None
    parts = (((candidates[0] or {}).get("content") or {}).get("parts") or [])
    text = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict))
    return _extract_json_text(text)


def _request_openai_compatible(
    endpoint: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any] | None:
    if not _is_usable_secret(api_key):
        return None
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        },
        timeout=30,
    )
    if not response.ok:
        return None
    data = response.json()
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return _extract_json_text(text)


def _request_claude(system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
    if not _is_usable_secret(CLAUDE_API_KEY):
        return None
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": CLAUDE_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": CLAUDE_MODEL,
            "max_tokens": 1200,
            "temperature": 0.1,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        },
        timeout=30,
    )
    if not response.ok:
        return None
    data = response.json()
    blocks = data.get("content") or []
    text = "\n".join(block.get("text", "") for block in blocks if isinstance(block, dict))
    return _extract_json_text(text)


def _get_api_ai_go_token() -> str | None:
    if not (
        _is_usable_secret(API_AI_GO_CONSUMER_KEY)
        and _is_usable_secret(API_AI_GO_CONSUMER_SECRET)
        and API_AI_GO_TOKEN_URL
        and API_AI_GO_ENDPOINT
    ):
        return None

    basic = base64.b64encode(
        f"{API_AI_GO_CONSUMER_KEY}:{API_AI_GO_CONSUMER_SECRET}".encode("utf-8")
    ).decode("ascii")
    response = requests.post(
        API_AI_GO_TOKEN_URL,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    if not response.ok:
        return None
    data = response.json()
    return data.get("access_token")


def _request_api_ai_go(system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
    token = _get_api_ai_go_token()
    if not token:
        return None
    response = requests.post(
        API_AI_GO_ENDPOINT,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "model": API_AI_GO_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        },
        timeout=30,
    )
    if not response.ok:
        return None
    data = response.json()
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return _extract_json_text(text)


def _classify_with_fallbacks(system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
    providers: list[tuple[str, Callable[[], dict[str, Any] | None]]] = [
        ("google", lambda: _request_google(system_prompt, user_prompt)),
        (
            "openai",
            lambda: _request_openai_compatible(
                "https://api.openai.com/v1/chat/completions",
                OPENAI_API_KEY,
                OPENAI_MODEL,
                system_prompt,
                user_prompt,
            ),
        ),
        ("claude", lambda: _request_claude(system_prompt, user_prompt)),
        (
            "xai",
            lambda: _request_openai_compatible(
                "https://api.x.ai/v1/chat/completions",
                XAI_API_KEY,
                XAI_MODEL,
                system_prompt,
                user_prompt,
            ),
        ),
        (
            "groq",
            lambda: _request_openai_compatible(
                "https://api.groq.com/openai/v1/chat/completions",
                GROQ_API_KEY,
                GROQ_MODEL,
                system_prompt,
                user_prompt,
            ),
        ),
        (
            "mistral",
            lambda: _request_openai_compatible(
                "https://api.mistral.ai/v1/chat/completions",
                MISTRAL_API_KEY,
                MISTRAL_MODEL,
                system_prompt,
                user_prompt,
            ),
        ),
        ("api_ai_go", lambda: _request_api_ai_go(system_prompt, user_prompt)),
    ]

    for provider_name, provider_call in providers:
        try:
            result = provider_call()
        except Exception:
            result = None
        if isinstance(result, dict):
            result.setdefault("ai_provider", provider_name)
            return result
    return None


def _chat_completion_request(payload: dict[str, Any]) -> requests.Response:
    if _is_usable_secret(LOVABLE_API_KEY):
        return requests.post(
            "https://ai.gateway.lovable.dev/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {LOVABLE_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )

    if _is_usable_secret(OPENAI_API_KEY):
        openai_payload = dict(payload)
        openai_payload["model"] = OPENAI_MODEL or payload.get("model") or "gpt-4o-mini"
        return requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=openai_payload,
            timeout=30,
        )

    raise RuntimeError("Nenhuma chave de IA válida configurada")


def classify_news(text_content: str, title: str, url: str, entity_name: str) -> dict[str, Any] | None:
    """Classify a news article for an entity using the AI gateway.

    Returns a dict with keys: title, content, sentiment, classification,
    people_mentioned, relevant — or None on failure.
    """
    truncated = _sanitize_news_text(text_content)
    if not truncated:
        truncated = (title or "")[:3000]

    with open("prompts/news_classifier.txt", encoding="utf-8") as f:
        system_prompt = f.read().replace("{{entity_name}}", entity_name)
    user_prompt = _build_user_prompt(title, url, truncated)
    result = _classify_with_fallbacks(system_prompt, user_prompt)
    if not isinstance(result, dict):
        return None

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
