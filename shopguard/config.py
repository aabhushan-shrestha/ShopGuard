"""Config loader with YAML reading, deep-merge defaults, and device auto-detection."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "camera": {
        "source": 0,
        "width": 1280,
        "height": 720,
        "fps_cap": 30,
        "reconnect_attempts": 5,
        "reconnect_delay": 2.0,
    },
    "model": {
        "weights": "yolov8n.pt",
        "confidence": 0.5,
        "classes": [0],
        "device": "auto",
        "img_size": 640,
    },
    "display": {
        "show_window": True,
        "window_name": "ShopGuard - Person Detection",
        "show_fps": True,
        "show_count": True,
        "bbox_color": [0, 255, 0],
        "bbox_thickness": 2,
        "font_scale": 0.6,
    },
    "logging": {
        "level": "INFO",
        "file": "logs/shopguard.log",
        "max_bytes": 5_242_880,
        "backup_count": 3,
        "format": "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    },
}


class AttrDict(dict):
    """Dict subclass that supports attribute access for nested keys."""

    def __getattr__(self, key: str) -> Any:
        try:
            val = self[key]
        except KeyError:
            raise AttributeError(f"Config has no key {key!r}") from None
        return val

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new AttrDict."""
    merged = AttrDict()
    for key in set(base) | set(override):
        b_val = base.get(key)
        o_val = override.get(key)
        if isinstance(b_val, dict) and isinstance(o_val, dict):
            merged[key] = _deep_merge(b_val, o_val)
        elif o_val is not None:
            merged[key] = o_val
        else:
            merged[key] = b_val
    return merged


def _resolve_device(device: str) -> str:
    """Pick the best available device when *device* is ``'auto'``."""
    if device != "auto":
        return device
    try:
        import torch
        if torch.cuda.is_available():
            selected = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            selected = "mps"
        else:
            selected = "cpu"
    except ImportError:
        selected = "cpu"
    logger.info("Auto-detected device: %s", selected)
    return selected


def load(path: str | Path = "config.yaml") -> AttrDict:
    """Load YAML config from *path*, merge with defaults, resolve device."""
    user_cfg: dict[str, Any] = {}
    path = Path(path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        logger.info("Loaded config from %s", path)
    else:
        logger.warning("Config file %s not found, using defaults", path)

    cfg = _deep_merge(DEFAULTS, user_cfg)
    cfg.model["device"] = _resolve_device(cfg.model["device"])
    return cfg
