"""Authentication helpers: API key (agents) and JWT (dashboard users)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from database import get_db

logger = logging.getLogger(__name__)

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer()
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24


def _jwt_secret() -> str:
    return os.environ.get("JWT_SECRET", "change-me")


# ── Passwords ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(payload: dict[str, Any]) -> str:
    data = payload.copy()
    data["exp"] = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode(data, _jwt_secret(), algorithm=JWT_ALGORITHM)


def _decode_jwt(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


# ── FastAPI dependencies ───────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> dict[str, Any]:
    return _decode_jwt(credentials.credentials)


def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_owner(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Access denied")
    return user


def get_store_by_api_key(api_key: str = Security(_api_key_header)) -> dict[str, Any]:
    """Look up a store by its API key; raise 401 if not found or inactive."""
    db = get_db()
    result = (
        db.table("stores")
        .select("*")
        .eq("api_key", api_key)
        .eq("is_active", True)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return result.data[0]
