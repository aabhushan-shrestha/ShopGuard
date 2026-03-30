"""YOLO-based person detector."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from ultralytics import YOLO

if TYPE_CHECKING:
    from shopguard.config import AttrDict

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Detection:
    """A single detected bounding box."""
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float

    @property
    def center(self) -> tuple[int, int]:
        return (self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1


class Detector:
    """Wraps a YOLO model for person detection."""

    def __init__(self, cfg: AttrDict) -> None:
        mcfg = cfg.model
        self._confidence = mcfg["confidence"]
        self._classes = mcfg["classes"]
        self._img_size = mcfg["img_size"]

        logger.info("Loading YOLO model %s on %s", mcfg["weights"], mcfg["device"])
        self._model = YOLO(mcfg["weights"])
        self._device = mcfg["device"]

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Run inference on *frame* and return a list of Detections."""
        results = self._model(
            frame,
            conf=self._confidence,
            classes=self._classes,
            imgsz=self._img_size,
            device=self._device,
            verbose=False,
        )
        detections: list[Detection] = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            detections.append(Detection(x1, y1, x2, y2, conf))
        return detections
