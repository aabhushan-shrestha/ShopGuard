"""Zone manager — polygon-based occupancy monitoring."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from shopguard.config import AttrDict
    from shopguard.detector import Detection

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Zone:
    """A named polygon region with an optional occupancy limit."""
    name: str
    points: list[tuple[int, int]]
    max_occupancy: int = 0  # 0 = unlimited
    color: tuple[int, int, int] = (0, 255, 255)

    @property
    def contour(self) -> np.ndarray:
        """Return points as a cv2-compatible contour array."""
        return np.array(self.points, dtype=np.int32)


@dataclass(slots=True)
class ZoneStatus:
    """Occupancy snapshot for a single zone after one frame."""
    zone: Zone
    count: int
    is_over_limit: bool
    detections: list[Detection] = field(default_factory=list)


class ZoneManager:
    """Loads zones from config and checks detection occupancy."""

    def __init__(self, cfg: AttrDict) -> None:
        self._zones: list[Zone] = []
        for z in cfg.get("zones", []):
            pts = [tuple(p) for p in z["points"]]
            color = tuple(z.get("color", [0, 255, 255]))
            zone = Zone(
                name=z["name"],
                points=pts,
                max_occupancy=z.get("max_occupancy", 0),
                color=color,
            )
            self._zones.append(zone)
        logger.info("Loaded %d zone(s): %s",
                     len(self._zones), [z.name for z in self._zones])

    @property
    def zones(self) -> list[Zone]:
        return self._zones

    def check_occupancy(self, detections: list[Detection]) -> list[ZoneStatus]:
        """Check which detections fall inside each zone."""
        statuses: list[ZoneStatus] = []
        for zone in self._zones:
            contour = zone.contour
            inside: list[Detection] = []
            for det in detections:
                cx, cy = det.center
                dist = cv2.pointPolygonTest(contour, (float(cx), float(cy)), False)
                if dist >= 0:  # inside or on edge
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
        """Draw semi-transparent zone overlays with occupancy labels."""
        overlay = frame.copy()
        for status in statuses:
            zone = status.zone
            pts = zone.contour
            # Filled polygon on overlay
            cv2.fillPoly(overlay, [pts], zone.color)
            # Border
            cv2.polylines(frame, [pts], isClosed=True, color=zone.color, thickness=2)

        # Blend overlay at 25% opacity
        cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)

        # Labels drawn after blending so they stay crisp
        for status in statuses:
            zone = status.zone
            pts = zone.contour
            # Place label at the topmost point of the polygon
            top_idx = pts[:, 1].argmin()
            lx, ly = int(pts[top_idx][0]), int(pts[top_idx][1]) - 10
            if zone.max_occupancy > 0:
                label = f"{zone.name}: {status.count}/{zone.max_occupancy}"
            else:
                label = f"{zone.name}: {status.count}"
            color = (0, 0, 255) if status.is_over_limit else zone.color
            cv2.putText(frame, label, (lx, ly),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        return frame
