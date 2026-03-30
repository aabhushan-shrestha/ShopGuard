"""Display renderer for bounding boxes, FPS, person count, and zone overlays."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from shopguard.behavior import SuspicionEvent
    from shopguard.config import AttrDict
    from shopguard.detector import Detection
    from shopguard.tracker import PersonTracker
    from shopguard.zones import ZoneManager, ZoneStatus

logger = logging.getLogger(__name__)


class Display:
    """Draws detections onto frames and manages the OpenCV window."""

    def __init__(self, cfg: AttrDict) -> None:
        dcfg = cfg.display
        self._show_window = dcfg["show_window"]
        self._window_name = dcfg["window_name"]
        self._show_fps = dcfg["show_fps"]
        self._show_count = dcfg["show_count"]
        self._bbox_color = tuple(dcfg["bbox_color"])
        self._bbox_thickness = dcfg["bbox_thickness"]
        self._font_scale = dcfg["font_scale"]
        self._prev_time = time.time()
        self._window_created = False

    def draw(
        self,
        frame: np.ndarray,
        detections: list[Detection],
        zone_manager: ZoneManager | None = None,
        zone_statuses: list[ZoneStatus] | None = None,
        tracked: list[tuple[int, Detection]] | None = None,
        suspicion_events: list[SuspicionEvent] | None = None,
    ) -> np.ndarray:
        """Draw bounding boxes, zone overlays, and HUD onto *frame* (mutates in place).

        If *tracked* is provided, person IDs are shown instead of raw detections.
        Suspicious persons are highlighted in red with their event type(s).
        """
        if zone_manager is not None and zone_statuses is not None:
            zone_manager.draw_zones(frame, zone_statuses)

        # Build per-person event type set for quick lookup
        event_types: dict[int, set[str]] = {}
        if suspicion_events:
            for ev in suspicion_events:
                event_types.setdefault(ev.person_id, set()).add(ev.type)

        items: list[tuple[int | None, str, Detection]]
        if tracked is not None:
            items = [(tid, f"ID {tid} {det.confidence:.2f}", det) for tid, det in tracked]
        else:
            items = [(None, f"person {det.confidence:.2f}", det) for det in detections]

        _ALERT_COLOR = (0, 0, 255)  # red for suspicious persons

        for tid, label, det in items:
            types = event_types.get(tid) if tid is not None else None
            color = _ALERT_COLOR if types else self._bbox_color
            if types:
                label = f"ID {tid} [{', '.join(sorted(types))}]"
            cv2.rectangle(
                frame, (det.x1, det.y1), (det.x2, det.y2),
                color, self._bbox_thickness,
            )
            cv2.putText(
                frame, label, (det.x1, det.y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, self._font_scale,
                color, 1,
            )

        # Alert banner: flash a red border + message when any suspicious event is active
        if event_types:
            h, w = frame.shape[:2]
            cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 255), 6)
            unique_types = sorted({t for ts in event_types.values() for t in ts})
            banner = "ALERT: " + ", ".join(unique_types).upper()
            cv2.putText(
                frame, banner, (10, h - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2,
            )

        now = time.time()
        fps = 1.0 / max(now - self._prev_time, 1e-6)
        self._prev_time = now

        overlay_color = (0, 200, 255)
        y_offset = 30
        if self._show_fps:
            cv2.putText(
                frame, f"FPS: {fps:.1f}", (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 1, overlay_color, 2,
            )
            y_offset += 35
        if self._show_count:
            cv2.putText(
                frame, f"Persons: {len(detections)}", (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 1, overlay_color, 2,
            )

        return frame

    def show(self, frame: np.ndarray) -> bool:
        """Display the frame. Returns False if the user wants to quit.

        In headless mode (show_window=false) always returns True.
        """
        if not self._show_window:
            return True

        if not self._window_created:
            cv2.namedWindow(self._window_name)
            self._window_created = True

        # Window closed via X button
        if cv2.getWindowProperty(self._window_name, cv2.WND_PROP_VISIBLE) < 1:
            logger.info("Window closed by user")
            return False

        cv2.imshow(self._window_name, frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q") or key == 27:
            logger.info("Quit key pressed")
            return False

        return True

    def cleanup(self) -> None:
        """Destroy the OpenCV window if it was created."""
        if self._window_created:
            cv2.destroyAllWindows()
            self._window_created = False
