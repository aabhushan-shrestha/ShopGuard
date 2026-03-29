"""Display renderer for bounding boxes, FPS, and person count overlay."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from shopguard.config import AttrDict
    from shopguard.detector import Detection

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
        self, frame: np.ndarray, detections: list[Detection]
    ) -> np.ndarray:
        """Draw bounding boxes and overlays onto *frame* (mutates in place)."""
        for det in detections:
            cv2.rectangle(
                frame, (det.x1, det.y1), (det.x2, det.y2),
                self._bbox_color, self._bbox_thickness,
            )
            label = f"person {det.confidence:.2f}"
            cv2.putText(
                frame, label, (det.x1, det.y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, self._font_scale,
                self._bbox_color, 1,
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
