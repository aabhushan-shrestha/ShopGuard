"""ShopGuard Cloud API — FastAPI entry point."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

from routers import admin, agent, auth_router, client  # noqa: E402

app = FastAPI(
    title="ShopGuard Cloud API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.shopguard.com",
        "https://admin.shopguard.com",
        "http://localhost:3000",   # local dashboard dev
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(agent.router,       prefix="/agent", tags=["agent"])
app.include_router(admin.router,       prefix="/admin", tags=["admin"])
app.include_router(client.router,      prefix="/client", tags=["client"])


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}
