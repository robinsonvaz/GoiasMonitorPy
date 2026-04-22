"""Application settings — pydantic-settings with .env support."""
from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    lovable_api_key: str = Field(default="")
    firecrawl_api_key: str = Field(default="")
    scrapingbee_api_key: str = Field(default="")


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
FIRECRAWL_API_KEY = settings.firecrawl_api_key
SCRAPINGBEE_API_KEY = settings.scrapingbee_api_key
