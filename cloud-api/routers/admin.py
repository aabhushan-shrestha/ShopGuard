"""Admin endpoints — JWT auth, admin role only.

GET  /admin/stores         — all stores
GET  /admin/alerts         — all alerts (filterable)
GET  /admin/clips          — all clips
GET  /admin/heartbeats     — agent liveness across all stores
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from auth import require_admin
from database import get_db
from models import AlertOut, ClipOut, HeartbeatOut, StoreOut

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/stores", response_model=list[StoreOut])
def admin_stores(
    _: dict[str, Any] = Depends(require_admin),
) -> list[StoreOut]:
    db = get_db()
    result = db.table("stores").select("*").order("created_at", desc=True).execute()
    return [StoreOut(**row) for row in result.data]


@router.get("/alerts", response_model=list[AlertOut])
def admin_alerts(
    store_id: str | None = Query(default=None),
    level: str | None = Query(default=None),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    _: dict[str, Any] = Depends(require_admin),
) -> list[AlertOut]:
    db = get_db()
    q = db.table("alerts").select("*").order("created_at", desc=True).range(offset, offset + limit - 1)
    if store_id:
        q = q.eq("store_id", store_id)
    if level:
        q = q.eq("level", level)
    result = q.execute()
    return [AlertOut(**row) for row in result.data]


@router.get("/clips", response_model=list[ClipOut])
def admin_clips(
    store_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict[str, Any] = Depends(require_admin),
) -> list[ClipOut]:
    db = get_db()
    q = db.table("clips").select("*").order("created_at", desc=True).range(offset, offset + limit - 1)
    if store_id:
        q = q.eq("store_id", store_id)
    result = q.execute()
    return [ClipOut(**row) for row in result.data]


@router.get("/heartbeats", response_model=list[HeartbeatOut])
def admin_heartbeats(
    _: dict[str, Any] = Depends(require_admin),
) -> list[HeartbeatOut]:
    db = get_db()
    result = db.table("heartbeats").select("*").order("last_seen", desc=True).execute()
    return [HeartbeatOut(**row) for row in result.data]
