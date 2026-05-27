"""Application settings — pydantic-settings with .env support."""
from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mysql_host: str = Field(default="127.0.0.1")
    mysql_port: int = Field(default=3306)
    mysql_user: str = Field(default="root")
    mysql_password: str = Field(
        default="root",
        validation_alias=AliasChoices("MYSQL_PASSWORD", "MYSQL_PASS"),
    )
    mysql_database: str = Field(
        default="goiasmonitor",
        validation_alias=AliasChoices("MYSQL_DATABASE", "MYSQL_DB"),
    )
    local_admin_email: str = Field(default="admin@local")
    local_admin_password: str = Field(default="admin123")
    local_admin_name: str = Field(default="Administrador Local")
    app_secret_key: str = Field(
        default="dev-secret-key",
        validation_alias=AliasChoices("APP_SECRET_KEY", "FLASK_SECRET_KEY"),
    )
    debug: bool = Field(
        default=False,
        validation_alias=AliasChoices("DEBUG", "FLASK_DEBUG"),
    )
    app_root_path: str = Field(default="")
    lovable_api_key: str = Field(default="")
    google_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_API_KEY", "GOOGLE_API_Key"),
    )
    google_model: str = Field(default="gemini-2.5-flash")
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    claude_api_key: str = Field(default="")
    claude_model: str = Field(default="claude-3-5-sonnet-20241022")
    xai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("XAI_API_KEY", "xAI_API_KEY"),
    )
    xai_model: str = Field(default="grok-3-mini")
    groq_api_key: str = Field(default="")
    groq_model: str = Field(default="llama-3.3-70b-versatile")
    mistral_api_key: str = Field(default="")
    mistral_model: str = Field(default="mistral-small-latest")
    huggingface_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("HUGGINGFACE_API_KEY"),
    )
    huggingface_model: str = Field(default="Qwen/Qwen2-7B-Instruct")
    cohere_api_key: str = Field(default="")
    cohere_model: str = Field(default="command-r-08-2024")
    cerebras_api_key: str = Field(default="")
    cerebras_model: str = Field(default="qwen-3-235b-a22b-instruct-2507")
    api_ai_go_consumer_key: str = Field(
        default="",
        validation_alias=AliasChoices("API_AI_GO_CONSUMER_KEY", "GEMINI_API_KEI_GOV"),
    )
    api_ai_go_consumer_secret: str = Field(default="")
    api_ai_go_token_url: str = Field(default="")
    api_ai_go_base_url: str = Field(default="")
    api_ai_go_endpoint: str = Field(default="")
    api_ai_go_model: str = Field(default="llama-31-8b-instruct")
    serper_api_key: str = Field(default="")
    serpapi_key: str = Field(default="")
    searchapi_api_key: str = Field(default="")
    searchapi_enabled: bool = Field(default=True)
    tavily_api_key: str = Field(default="")
    jina_api_key: str = Field(default="")
    playwright_enabled: bool = Field(default=True)
    web_provider_cooldown_seconds: int = Field(default=120)
    llm_provider_cooldown_seconds: int = Field(default=180)
    firecrawl_api_key: str = Field(default="")
    scrapingbee_api_key: str = Field(default="")
    rss_feeds: list[str] = Field(default_factory=list)
    google_alerts_rss: list[str] = Field(default_factory=list)
    news_collection_workers: int = Field(default=4)
    news_classifier_max_chars: int = Field(default=120000)
    ai_request_timeout_seconds: int = Field(default=30)


settings = Settings()

# Backward-compat module-level aliases (used by db.py, agents, and tools)
MYSQL_HOST = settings.mysql_host
MYSQL_PORT = settings.mysql_port
MYSQL_USER = settings.mysql_user
MYSQL_PASSWORD = settings.mysql_password
MYSQL_DATABASE = settings.mysql_database
LOCAL_ADMIN_EMAIL = settings.local_admin_email
LOCAL_ADMIN_PASSWORD = settings.local_admin_password
LOCAL_ADMIN_NAME = settings.local_admin_name
FLASK_SECRET_KEY = settings.app_secret_key
FLASK_DEBUG = settings.debug
LOVABLE_API_KEY = settings.lovable_api_key
GOOGLE_API_KEY = settings.google_api_key
GOOGLE_MODEL = settings.google_model
OPENAI_API_KEY = settings.openai_api_key
OPENAI_MODEL = settings.openai_model
CLAUDE_API_KEY = settings.claude_api_key
CLAUDE_MODEL = settings.claude_model
XAI_API_KEY = settings.xai_api_key
XAI_MODEL = settings.xai_model
GROQ_API_KEY = settings.groq_api_key
GROQ_MODEL = settings.groq_model
MISTRAL_API_KEY = settings.mistral_api_key
MISTRAL_MODEL = settings.mistral_model
HUGGINGFACE_API_KEY = settings.huggingface_api_key
HUGGINGFACE_MODEL = settings.huggingface_model
COHERE_API_KEY = settings.cohere_api_key
COHERE_MODEL = settings.cohere_model
CEREBRAS_API_KEY = settings.cerebras_api_key
CEREBRAS_MODEL = settings.cerebras_model
API_AI_GO_CONSUMER_KEY = settings.api_ai_go_consumer_key
API_AI_GO_CONSUMER_SECRET = settings.api_ai_go_consumer_secret
API_AI_GO_TOKEN_URL = settings.api_ai_go_token_url
API_AI_GO_BASE_URL = settings.api_ai_go_base_url
API_AI_GO_ENDPOINT = settings.api_ai_go_endpoint
API_AI_GO_MODEL = settings.api_ai_go_model
SERPER_API_KEY = settings.serper_api_key
SERPAPI_KEY = settings.serpapi_key
SEARCHAPI_API_KEY = settings.searchapi_api_key
SEARCHAPI_ENABLED = settings.searchapi_enabled
TAVILY_API_KEY = settings.tavily_api_key
JINA_API_KEY = settings.jina_api_key
PLAYWRIGHT_ENABLED = settings.playwright_enabled
WEB_PROVIDER_COOLDOWN_SECONDS = max(10, settings.web_provider_cooldown_seconds)
LLM_PROVIDER_COOLDOWN_SECONDS = max(10, settings.llm_provider_cooldown_seconds)
FIRECRAWL_API_KEY = settings.firecrawl_api_key
SCRAPINGBEE_API_KEY = settings.scrapingbee_api_key
RSS_FEEDS = settings.rss_feeds
GOOGLE_ALERTS_RSS = settings.google_alerts_rss
NEWS_COLLECTION_WORKERS = max(1, settings.news_collection_workers)
NEWS_CLASSIFIER_MAX_CHARS = max(1000, settings.news_classifier_max_chars)
AI_REQUEST_TIMEOUT_SECONDS = max(5, settings.ai_request_timeout_seconds)
