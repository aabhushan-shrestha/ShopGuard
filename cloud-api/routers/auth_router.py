"""POST /auth/login — returns JWT for dashboard users."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from auth import create_access_token, verify_password
from database import get_db
from models import LoginIn, TokenOut

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn) -> TokenOut:
    db = get_db()
    result = db.table("users").select("*").eq("email", body.email).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = result.data[0]
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({
        "sub": user["id"],
        "role": user["role"],
        "store_id": user.get("store_id"),
    })
    logger.info("Login: %s (%s)", user["email"], user["role"])
    return TokenOut(access_token=token)
