"""Pydantic domain models for GoiasMonitorPy."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserSession(BaseModel):
    id: str
    email: str
    full_name: str = ""


class EntityIn(BaseModel):
    name: str = Field(..., min_length=1)
    entity_type: str = "orgao"
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)


class EntityOut(EntityIn):
    id: str
    is_active: bool = True
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NewsItem(BaseModel):
    id: str
    entity_id: str | None = None
    title: str | None = None
    content: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    classification: str | None = None
    sentiment: str | None = None
    people_mentioned: list[str] = Field(default_factory=list)
    collected_at: datetime | None = None


class AlertOut(BaseModel):
    id: str
    user_id: str
    news_item_id: str | None = None
    title: str | None = None
    message: str | None = None
    alert_type: str = "info"
    is_read: bool = False
    created_at: datetime | None = None


class CollectRequest(BaseModel):
    entity_id: str | None = None


class CollectResult(BaseModel):
    success: bool
    collected: int = 0
    error: str | None = None
    message: str | None = None
    credits_exhausted: bool = False
    fallback_used: bool = False
