"""Camera wrapper with auto-reconnect and context manager support."""

from __future__ import annotations

import logging
import threading
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
        self._lock = threading.Lock()

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
        new_cap = cv2.VideoCapture(src)
        new_cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cfg["width"])
        new_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cfg["height"])

        if not new_cap.isOpened():
            raise RuntimeError(f"Cannot open camera source {src}")
        with self._lock:
            self._cap = new_cap
        logger.info("Camera opened (source=%s, %dx%d)",
                     src, self._cfg["width"], self._cfg["height"])

    def release(self) -> None:
        """Release the underlying VideoCapture."""
        with self._lock:
            cap = self._cap
            self._cap = None
        if cap is not None:
            cap.release()
            logger.info("Camera released")

    def read(self) -> np.ndarray:
        """Read a single frame, reconnecting on failure.

        Returns the decoded frame (BGR numpy array).
        Raises ``RuntimeError`` if reconnection is exhausted.
        """
        with self._lock:
            cap = self._cap
        if cap is not None:
            ret, frame = cap.read()
            if ret:
                return frame
            logger.warning("Frame read failed, attempting reconnect")
        self._reconnect()
        with self._lock:
            cap = self._cap
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError("Frame read failed after reconnect")
        return frame

    def frames(self) -> Generator[np.ndarray, None, None]:
        """Yield frames continuously, reconnecting as needed."""
        while True:
            yield self.read()

    def switch_source(self, source: int) -> None:
        """Switch to a different camera source at runtime (thread-safe)."""
        with self._lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None
            new_cap = cv2.VideoCapture(source)
            new_cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cfg["width"])
            new_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cfg["height"])
            if not new_cap.isOpened():
                raise RuntimeError(f"Cannot open camera source {source}")
            self._cap = new_cap
            self._cfg = dict(self._cfg)   # make mutable copy
            self._cfg["source"] = source
            logger.info("Camera switched to source %s", source)

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
