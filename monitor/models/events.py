"""Eventos de aplicação registados no histórico."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from monitor.models.enums import EventType


class ApplicationEvent(BaseModel):
    event_type: EventType
    property_id: int | None = None
    source: str | None = None
    message: str = ""
    previous_value: Any = None
    new_value: Any = None
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
