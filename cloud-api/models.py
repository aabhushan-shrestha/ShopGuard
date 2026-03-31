"""Pydantic request/response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ── Agent request bodies ───────────────────────────────────────────────────────

class RegisterIn(BaseModel):
    name: str
    address: str = ""
    agent_version: str = "unknown"
    register_secret: str  # must match AGENT_REGISTER_SECRET env var


class HeartbeatIn(BaseModel):
    camera_index: int
    agent_version: str = "unknown"


class AlertIn(BaseModel):
    camera_index: int
    level: str          # info | warning | critical
    alert_type: str
    message: str
    zone_name: str | None = None
    person_id: int | None = None
    timestamp: str      # ISO-8601


class ClipMetaIn(BaseModel):
    camera_index: int
    alert_id: str | None = None
    filename: str
    duration_seconds: float | None = None


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Generic responses ─────────────────────────────────────────────────────────

class OkOut(BaseModel):
    ok: bool = True
    detail: str = ""


class StoreOut(BaseModel):
    id: str
    name: str
    address: str
    plan: str
    is_active: bool
    created_at: str


class AlertOut(BaseModel):
    id: str
    store_id: str
    camera_index: int
    level: str
    alert_type: str
    message: str
    zone_name: str | None
    person_id: int | None
    timestamp: str
    created_at: str


class ClipOut(BaseModel):
    id: str
    store_id: str
    camera_index: int
    alert_id: str | None
    filename: str
    storage_url: str
    duration_seconds: float | None
    created_at: str


class HeartbeatOut(BaseModel):
    store_id: str
    camera_index: int
    last_seen: str
    agent_version: str


class ZoneOut(BaseModel):
    store_id: str
    camera_index: int
    data: list[Any]
    updated_at: str
