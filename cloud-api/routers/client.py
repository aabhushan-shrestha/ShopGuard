"""Client endpoints — JWT auth, owner role. Scoped to caller's store.

GET    /client/alerts          — this store's alerts
GET    /client/clips           — this store's clips
GET    /client/zones/{camera}  — zone config for a camera
PUT    /client/zones/{camera}  — update zone config (synced to agent in Phase C)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import require_owner
from database import get_db
from models import AlertOut, ClipOut, ZoneOut

logger = logging.getLogger(__name__)
router = APIRouter()


def _store_id(user: dict[str, Any]) -> str:
    sid = user.get("store_id")
    if not sid:
        raise HTTPException(status_code=403, detail="No store associated with this account")
    return sid


@router.get("/alerts", response_model=list[AlertOut])
def client_alerts(
    level: str | None = Query(default=None),
    camera_index: int | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict[str, Any] = Depends(require_owner),
) -> list[AlertOut]:
    db = get_db()
    store_id = _store_id(user)
    q = (
        db.table("alerts")
        .select("*")
        .eq("store_id", store_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if level:
        q = q.eq("level", level)
    if camera_index is not None:
        q = q.eq("camera_index", camera_index)
    result = q.execute()
    return [AlertOut(**row) for row in result.data]


@router.get("/clips", response_model=list[ClipOut])
def client_clips(
    camera_index: int | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict[str, Any] = Depends(require_owner),
) -> list[ClipOut]:
    db = get_db()
    store_id = _store_id(user)
    q = (
        db.table("clips")
        .select("*")
        .eq("store_id", store_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if camera_index is not None:
        q = q.eq("camera_index", camera_index)
    result = q.execute()
    return [ClipOut(**row) for row in result.data]


@router.get("/zones/{camera_index}", response_model=ZoneOut)
def client_zones_get(
    camera_index: int,
    user: dict[str, Any] = Depends(require_owner),
) -> ZoneOut:
    db = get_db()
    store_id = _store_id(user)
    result = (
        db.table("zones")
        .select("*")
        .eq("store_id", store_id)
        .eq("camera_index", camera_index)
        .execute()
    )
    if not result.data:
        # Return empty zones rather than 404 — agent may not have synced yet
        return ZoneOut(
            store_id=store_id,
            camera_index=camera_index,
            data=[],
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    return ZoneOut(**result.data[0])


@router.put("/zones/{camera_index}", response_model=ZoneOut)
def client_zones_put(
    camera_index: int,
    body: list[Any],
    user: dict[str, Any] = Depends(require_owner),
) -> ZoneOut:
    """Update zone config. The agent will pull these on next sync (Phase C)."""
    db = get_db()
    store_id = _store_id(user)
    now = datetime.now(timezone.utc).isoformat()
    result = db.table("zones").upsert({
        "store_id": store_id,
        "camera_index": camera_index,
        "data": body,
        "updated_at": now,
    }).execute()
    return ZoneOut(**result.data[0])
