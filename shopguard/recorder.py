"""Ring-buffer clip recorder — saves video evidence around alert events."""

from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from shopguard.alerts import Alert
    from shopguard.config import AttrDict

logger = logging.getLogger(__name__)


@dataclass
class _Session:
    """State for one in-progress recording."""
    pre_frames: list[np.ndarray]
    alert: Alert
    post_frames: list[np.ndarray] = field(default_factory=list)
    remaining: int = 0


class ClipRecorder:
    """
    Continuously buffers annotated frames in a ring buffer.

    When ``trigger(alert)`` is called the current buffer is captured as
    pre-event footage and the recorder collects ``post_seconds`` more
    frames.  Once the post window closes the clip is written to disk with
    cv2.VideoWriter.  A JPEG snapshot is also saved at the trigger moment.

    Memory note: frames are optionally downscaled (``buffer_resize``) before
    being stored.  At 0.5× scale and 15 fps a 10 s pre-buffer ≈ 100 MB.
    Reduce ``pre_seconds``, ``fps``, or ``buffer_resize`` if memory is tight.
    """

    def __init__(self, cfg: AttrDict) -> None:
        rcfg = cfg.get("recorder", {})
        self._enabled: bool = rcfg.get("enabled", True)
        self._clips_dir = Path(rcfg.get("clips_dir", "clips"))
        self._pre_seconds: float = float(rcfg.get("pre_seconds", 10))
        self._post_seconds: float = float(rcfg.get("post_seconds", 10))
        self._record_fps: float = float(rcfg.get("fps", 15))
        self._save_snapshot: bool = rcfg.get("save_snapshot", True)
        self._resize: float = float(rcfg.get("buffer_resize", 0.5))

        # Sub-sample every N-th live frame to hit record_fps
        camera_fps = float(cfg.camera.get("fps_cap", 30))
        self._sample_interval: int = max(1, round(camera_fps / self._record_fps))

        buf_len = max(1, int(self._pre_seconds * self._record_fps))
        self._buffer: collections.deque[np.ndarray] = collections.deque(maxlen=buf_len)
        self._post_needed: int = max(1, int(self._post_seconds * self._record_fps))

        self._sessions: list[_Session] = []
        self._frame_count: int = 0

        if self._enabled:
            self._clips_dir.mkdir(parents=True, exist_ok=True)
            logger.info(
                "ClipRecorder: pre=%.0fs post=%.0fs record_fps=%.0f "
                "buf=%d sample_every=%d dir=%s",
                self._pre_seconds, self._post_seconds, self._record_fps,
                buf_len, self._sample_interval, self._clips_dir,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def push_frame(self, frame: np.ndarray) -> None:
        """Feed an annotated frame into the buffer (call every camera frame)."""
        if not self._enabled:
            return

        self._frame_count += 1
        if self._frame_count % self._sample_interval != 0:
            return  # sub-sample to keep buffer at record_fps

        stored = self._downscale(frame)
        self._buffer.append(stored)

        # Feed open sessions
        done: list[_Session] = []
        for session in self._sessions:
            session.post_frames.append(stored)
            session.remaining -= 1
            if session.remaining <= 0:
                done.append(session)

        for session in done:
            self._sessions.remove(session)
            self._write_clip(session)

    def trigger(self, alert: Alert) -> None:
        """Start a new recording session triggered by *alert*."""
        if not self._enabled:
            return

        pre = list(self._buffer)   # snapshot of ring buffer
        session = _Session(
            pre_frames=pre,
            alert=alert,
            remaining=self._post_needed,
        )
        self._sessions.append(session)
        logger.info(
            "ClipRecorder: triggered by '%s' (pre=%d frames, collecting %d post)",
            alert.alert_type, len(pre), self._post_needed,
        )
        if self._save_snapshot and pre:
            self._write_snapshot(pre[-1], alert)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _downscale(self, frame: np.ndarray) -> np.ndarray:
        if self._resize == 1.0:
            return frame.copy()
        h, w = frame.shape[:2]
        new_w = max(1, int(w * self._resize))
        new_h = max(1, int(h * self._resize))
        return cv2.resize(frame, (new_w, new_h))

    def _stem(self, alert: Alert) -> str:
        ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(alert.timestamp))
        return f"{ts}_{alert.alert_type}"

    def _write_clip(self, session: _Session) -> None:
        frames = session.pre_frames + session.post_frames
        if not frames:
            logger.warning("ClipRecorder: empty clip for '%s', skipping", session.alert.alert_type)
            return

        h, w = frames[0].shape[:2]
        out_path = self._clips_dir / f"{self._stem(session.alert)}.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, self._record_fps, (w, h))
        for f in frames:
            writer.write(f)
        writer.release()
        logger.info(
            "ClipRecorder: saved %d-frame clip → %s", len(frames), out_path,
        )

    def _write_snapshot(self, frame: np.ndarray, alert: Alert) -> None:
        out_path = self._clips_dir / f"{self._stem(alert)}_snapshot.jpg"
        cv2.imwrite(str(out_path), frame)
        logger.info("ClipRecorder: saved snapshot → %s", out_path)
