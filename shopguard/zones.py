"""Zone manager — polygon-based occupancy monitoring."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np

if TYPE_CHECKING:
    from shopguard.config import AttrDict
    from shopguard.detector import Detection

logger = logging.getLogger(__name__)

def get_zones_path(source: int) -> Path:
    return Path(f"config/zones_camera_{source}.json")

# Keep JSON_PATH as an alias for backwards compatibility
JSON_PATH = get_zones_path(0)

_COLOR_NORMAL: tuple[int, int, int] = (0, 200, 0)     # green
_COLOR_RESTRICTED: tuple[int, int, int] = (32, 32, 255)  # red
_COLOR_OVER_LIMIT: tuple[int, int, int] = (0, 0, 255)   # bright red


@dataclass(frozen=True, slots=True)
class Zone:
    """A named polygon region with an optional occupancy limit."""
    name: str
    points: list[tuple[int, int]]
    max_occupancy: int = 0  # 0 = unlimited
    restricted: bool = False
    color: tuple[int, int, int] = (0, 200, 0)

    @property
    def contour(self) -> np.ndarray:
        """Return points as a cv2-compatible contour array."""
        return np.array(self.points, dtype=np.int32)

    def display_color(self, is_over_limit: bool = False) -> tuple[int, int, int]:
        """Return the display color based on zone state."""
        if is_over_limit:
            return _COLOR_OVER_LIMIT
        if self.restricted:
            return _COLOR_RESTRICTED
        return _COLOR_NORMAL


@dataclass(slots=True)
class ZoneStatus:
    """Occupancy snapshot for a single zone after one frame."""
    zone: Zone
    count: int
    is_over_limit: bool
    detections: list[Detection] = field(default_factory=list)


def _zones_from_list(zone_list: list[dict[str, Any]]) -> list[Zone]:
    zones: list[Zone] = []
    for z in zone_list:
        pts: list[tuple[int, int]] = [tuple(p) for p in z["points"]]  # type: ignore[misc]
        color: tuple[int, int, int] = tuple(z.get("color", [0, 200, 0]))  # type: ignore[assignment]
        restricted = bool(z.get("restricted", False))
        zones.append(Zone(
            name=z["name"],
            points=pts,
            max_occupancy=int(z.get("max_occupancy", 0)),
            restricted=restricted,
            color=color,
        ))
    return zones


class ZoneManager:
    """Loads zones from config/zones.json (or YAML config) and checks detection occupancy."""

    def __init__(self, cfg: AttrDict) -> None:
        json_path = Path(cfg.get("zones_json", str(get_zones_path(0))))
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            zone_list = data if isinstance(data, list) else data.get("zones", [])
            self._zones = _zones_from_list(zone_list)
            logger.info("Loaded %d zone(s) from %s: %s",
                        len(self._zones), json_path, [z.name for z in self._zones])
        else:
            self._zones = _zones_from_list(cfg.get("zones", []))
            logger.info("Loaded %d zone(s) from config: %s",
                        len(self._zones), [z.name for z in self._zones])

    @property
    def zones(self) -> list[Zone]:
        return self._zones

    def reload(self, path: Path | None = None) -> None:
        """Re-read zones from *path* (or camera 0's path) if it exists."""
        target = path or get_zones_path(0)
        if target.exists():
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._zones = _zones_from_list(data)
            else:
                self._zones = _zones_from_list(data.get("zones", []))
            logger.info("ZoneManager: reloaded %d zone(s) from %s", len(self._zones), target)
        else:
            self._zones = []
            logger.info("ZoneManager: no zones file at %s, cleared zones", target)

    def save_to_json(self, path: Path | str = JSON_PATH) -> None:
        """Persist current zones to *path* as JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "zones": [
                {
                    "name": z.name,
                    "points": [list(p) for p in z.points],
                    "max_occupancy": z.max_occupancy,
                    "restricted": z.restricted,
                    "color": list(z.color),
                }
                for z in self._zones
            ]
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved %d zone(s) to %s", len(self._zones), path)

    def check_occupancy(self, detections: list[Detection]) -> list[ZoneStatus]:
        """Check which detections fall inside each zone."""
        statuses: list[ZoneStatus] = []
        for zone in self._zones:
            contour = zone.contour
            inside: list[Detection] = []
            for det in detections:
                cx, cy = det.center
                dist = cv2.pointPolygonTest(contour, (float(cx), float(cy)), False)
                if dist >= 0:
                    inside.append(det)
            over = zone.max_occupancy > 0 and len(inside) > zone.max_occupancy
            statuses.append(ZoneStatus(
                zone=zone,
                count=len(inside),
                is_over_limit=over,
                detections=inside,
            ))
        return statuses

    def draw_zones(self, frame: np.ndarray, statuses: list[ZoneStatus]) -> np.ndarray:
        """Draw semi-transparent zone overlays with occupancy labels.

        Green = normal zone, red = restricted zone, bright red = over limit.
        """
        overlay = frame.copy()
        for status in statuses:
            zone = status.zone
            pts = zone.contour
            color = zone.display_color(status.is_over_limit)
            cv2.fillPoly(overlay, [pts], color)
            cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)

        cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)

        for status in statuses:
            zone = status.zone
            pts = zone.contour
            top_idx = pts[:, 1].argmin()
            lx, ly = int(pts[top_idx][0]), int(pts[top_idx][1]) - 10
            if zone.max_occupancy > 0:
                label = f"{zone.name}: {status.count}/{zone.max_occupancy}"
            else:
                label = f"{zone.name}: {status.count}"
            label_color = zone.display_color(status.is_over_limit)
            cv2.putText(frame, label, (lx, ly),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, label_color, 2)

        return frame
