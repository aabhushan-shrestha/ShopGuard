"""Logging setup with console and rotating file handler."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shopguard.config import AttrDict


def setup(cfg: AttrDict) -> logging.Logger:
    """Configure the ``shopguard`` logger from *cfg.logging* settings."""
    log_cfg = cfg.logging

    log_path = Path(log_cfg["file"])
    log_path.parent.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(log_cfg["format"])
    level = getattr(logging, log_cfg["level"].upper(), logging.INFO)

    root_logger = logging.getLogger("shopguard")
    root_logger.setLevel(level)

    # Avoid duplicate handlers on repeated calls
    if root_logger.handlers:
        return root_logger

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(fmt)
    root_logger.addHandler(console)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=log_cfg["max_bytes"],
        backupCount=log_cfg["backup_count"],
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    return root_logger
