"""Camera wrapper with auto-reconnect and context manager support."""

from __future__ import annotations

import logging
import time
from typing import Generator, TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from shopguard.config import AttrDict

logger = logging.getLogger(__name__)


class Camera:
    """OpenCV VideoCapture wrapper with exponential-backoff reconnection."""

    def __init__(self, cfg: AttrDict) -> None:
        self._cfg = cfg.camera
        self._cap: cv2.VideoCapture | None = None

    # -- context manager --------------------------------------------------

    def __enter__(self) -> Camera:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()

    # -- public api -------------------------------------------------------

    def open(self) -> None:
        """Open the video source and apply resolution settings."""
        src = self._cfg["source"]
        self._cap = cv2.VideoCapture(src)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cfg["width"])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cfg["height"])

        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera source {src}")
        logger.info("Camera opened (source=%s, %dx%d)",
                     src, self._cfg["width"], self._cfg["height"])

    def release(self) -> None:
        """Release the underlying VideoCapture."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("Camera released")

    def read(self) -> np.ndarray:
        """Read a single frame, reconnecting on failure.

        Returns the decoded frame (BGR numpy array).
        Raises ``RuntimeError`` if reconnection is exhausted.
        """
        if self._cap is not None:
            ret, frame = self._cap.read()
            if ret:
                return frame
            logger.warning("Frame read failed, attempting reconnect")

        self._reconnect()
        ret, frame = self._cap.read()  # type: ignore[union-attr]
        if not ret:
            raise RuntimeError("Frame read failed after reconnect")
        return frame

    def frames(self) -> Generator[np.ndarray, None, None]:
        """Yield frames continuously, reconnecting as needed."""
        while True:
            yield self.read()

    def switch_source(self, source: int) -> None:
        """Release the current capture and reopen with *source*."""
        logger.info("Camera: switching to source %d", source)
        self.release()
        self._cap = cv2.VideoCapture(source)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cfg["width"])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cfg["height"])
        if not self._cap.isOpened():
            self._cap = None
            raise RuntimeError(f"Cannot open camera source {source}")
        logger.info("Camera switched to source %d (%dx%d)",
                    source, self._cfg["width"], self._cfg["height"])

    # -- internals --------------------------------------------------------

    def _reconnect(self) -> None:
        attempts = self._cfg["reconnect_attempts"]
        base_delay = self._cfg["reconnect_delay"]

        for i in range(1, attempts + 1):
            delay = base_delay * (2 ** (i - 1))
            logger.info("Reconnect attempt %d/%d (waiting %.1fs)", i, attempts, delay)
            time.sleep(delay)
            self.release()
            try:
                self.open()
                return
            except RuntimeError:
                logger.warning("Reconnect attempt %d failed", i)

        raise RuntimeError(
            f"Camera reconnection failed after {attempts} attempts"
        )
