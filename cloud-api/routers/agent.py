"""Agent endpoints — authenticated via X-API-Key header.

POST /agent/register   — first-boot store registration
POST /agent/heartbeat  — periodic liveness ping
POST /agent/alert      — forward a fired alert
POST /agent/clip       — upload a clip file + metadata
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from auth import get_store_by_api_key
from database import get_db
from models import AlertIn, ClipMetaIn, HeartbeatIn, OkOut, RegisterIn

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Register ──────────────────────────────────────────────────────────────────

@router.post("/register")
def agent_register(body: RegisterIn) -> dict[str, Any]:
    """Create a store on first boot, or return existing store info.

    Requires ``register_secret`` to match the ``AGENT_REGISTER_SECRET`` env var
    so arbitrary agents cannot create stores.
    """
    expected = os.environ.get("AGENT_REGISTER_SECRET", "")
    if not expected or body.register_secret != expected:
        raise HTTPException(status_code=403, detail="Invalid register secret")

    db = get_db()

    # Idempotent: return existing store if name already registered
    existing = db.table("stores").select("id,api_key,name").eq("name", body.name).execute()
    if existing.data:
        store = existing.data[0]
        logger.info("Register (existing): %s (%s)", store["name"], store["id"])
        return {"store_id": store["id"], "api_key": store["api_key"], "created": False}

    api_key = secrets.token_urlsafe(32)
    result = db.table("stores").insert({
        "name": body.name,
        "address": body.address,
        "api_key": api_key,
    }).execute()
    store = result.data[0]
    logger.info("Register (new): %s (%s)", store["name"], store["id"])
    return {"store_id": store["id"], "api_key": api_key, "created": True}


# ── Heartbeat ─────────────────────────────────────────────────────────────────

@router.post("/heartbeat", response_model=OkOut)
def agent_heartbeat(
    body: HeartbeatIn,
    store: dict[str, Any] = Depends(get_store_by_api_key),
) -> OkOut:
    db = get_db()
    db.table("heartbeats").upsert({
        "store_id": store["id"],
        "camera_index": body.camera_index,
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "agent_version": body.agent_version,
    }).execute()
    return OkOut()


# ── Alert ─────────────────────────────────────────────────────────────────────

@router.post("/alert")
def agent_alert(
    body: AlertIn,
    store: dict[str, Any] = Depends(get_store_by_api_key),
) -> dict[str, Any]:
    db = get_db()
    result = db.table("alerts").insert({
        "store_id": store["id"],
        "camera_index": body.camera_index,
        "level": body.level,
        "alert_type": body.alert_type,
        "message": body.message,
        "zone_name": body.zone_name,
        "person_id": body.person_id,
        "timestamp": body.timestamp,
    }).execute()
    alert = result.data[0]
    logger.info("Alert stored: %s / %s (store=%s)", body.level, body.alert_type, store["id"])
    return {"ok": True, "alert_id": alert["id"]}


# ── Clip upload ───────────────────────────────────────────────────────────────

@router.post("/clip")
async def agent_clip(
    camera_index: int = Form(...),
    filename: str = Form(...),
    alert_id: str | None = Form(default=None),
    duration_seconds: float | None = Form(default=None),
    file: UploadFile = File(...),
    store: dict[str, Any] = Depends(get_store_by_api_key),
) -> dict[str, Any]:
    db = get_db()
    bucket = os.environ.get("CLIPS_BUCKET", "clips")
    storage_path = f"{store['id']}/{filename}"

    content = await file.read()
    db.storage.from_(bucket).upload(
        storage_path,
        content,
        {"content-type": "video/mp4"},
    )

    public_url = db.storage.from_(bucket).get_public_url(storage_path)

    result = db.table("clips").insert({
        "store_id": store["id"],
        "camera_index": camera_index,
        "alert_id": alert_id,
        "filename": filename,
        "storage_url": public_url,
        "duration_seconds": duration_seconds,
    }).execute()
    clip = result.data[0]
    logger.info("Clip stored: %s (store=%s)", filename, store["id"])
    return {"ok": True, "clip_id": clip["id"], "storage_url": public_url}
