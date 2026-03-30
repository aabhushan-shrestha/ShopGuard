"""Rule-based behavior analysis: loitering, zone violations, and pacing."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from shopguard.config import AttrDict
    from shopguard.tracker import Track
    from shopguard.zones import Zone

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SuspicionEvent:
    """A suspicious behavior event for a specific tracked person."""
    type: str           # "loitering" | "zone_violation" | "pacing"
    person_id: int
    confidence: float   # 0.0 – 1.0
    timestamp: float
    zone_name: str | None = None


def _in_zone(cx: int, cy: int, zone: Zone) -> bool:
    return cv2.pointPolygonTest(zone.contour, (float(cx), float(cy)), False) >= 0


class BehaviorAnalyzer:
    """Analyzes per-person tracking history and zone membership each frame."""

    def __init__(self, cfg: AttrDict) -> None:
        bcfg = cfg.get("behavior", {})
        self._loiter_frames: int = int(bcfg.get("loiter_frames", 150))
        self._pace_reversals: int = int(bcfg.get("pace_reversals", 4))
        self._pace_window: int = int(bcfg.get("pace_window", 90))
        # dwell[person_id][zone_name] = consecutive frames inside that zone
        self._dwell: dict[int, dict[str, int]] = {}
        # last_logged[(person_id, event_type)] = timestamp — throttles log spam
        self._last_logged: dict[tuple[int, str], float] = {}
        logger.info(
            "BehaviorAnalyzer: loiter_frames=%d, pace_reversals=%d, pace_window=%d",
            self._loiter_frames, self._pace_reversals, self._pace_window,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        tracks: dict[int, Track],
        zones: list[Zone],
    ) -> list[SuspicionEvent]:
        """Return suspicion events for the current frame.

        Called once per frame; may return multiple events per person.
        """
        now = time.time()
        events: list[SuspicionEvent] = []

        # Clean up dwell state for persons no longer on screen
        for pid in list(self._dwell.keys()):
            if pid not in tracks:
                del self._dwell[pid]

        for tid, track in tracks.items():
            cx, cy = track.detection.center
            in_zones = [z for z in zones if _in_zone(cx, cy, z)]

            # Maintain dwell counters
            if tid not in self._dwell:
                self._dwell[tid] = {}
            for zone in zones:
                if zone in in_zones:
                    self._dwell[tid][zone.name] = self._dwell[tid].get(zone.name, 0) + 1
                else:
                    self._dwell[tid][zone.name] = 0

            # --- Rule 1: zone violation (restricted zone entry) ---
            for zone in in_zones:
                if zone.restricted:
                    self._log_once(tid, "zone_violation", now,
                                   "Zone violation: person %d entered restricted zone '%s'",
                                   tid, zone.name)
                    events.append(SuspicionEvent(
                        type="zone_violation",
                        person_id=tid,
                        confidence=1.0,
                        timestamp=now,
                        zone_name=zone.name,
                    ))

            # --- Rule 2: loitering (dwelling too long in any zone) ---
            for zone in in_zones:
                dwell = self._dwell[tid].get(zone.name, 0)
                if dwell >= self._loiter_frames:
                    conf = min(1.0, dwell / (self._loiter_frames * 2))
                    self._log_once(tid, "loitering", now,
                                   "Loitering: person %d in zone '%s' for %d frames (conf=%.2f)",
                                   tid, zone.name, dwell, conf)
                    events.append(SuspicionEvent(
                        type="loitering",
                        person_id=tid,
                        confidence=conf,
                        timestamp=now,
                        zone_name=zone.name,
                    ))

            # --- Rule 3: pacing (back-and-forth movement) ---
            pace_conf = self._detect_pacing(track.history)
            if pace_conf > 0:
                zone_name = in_zones[0].name if in_zones else None
                self._log_once(tid, "pacing", now,
                               "Pacing: person %d (conf=%.2f)", tid, pace_conf)
                events.append(SuspicionEvent(
                    type="pacing",
                    person_id=tid,
                    confidence=pace_conf,
                    timestamp=now,
                    zone_name=zone_name,
                ))

        return events

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_pacing(self, history: list[tuple[int, int]]) -> float:
        """Return a confidence score for back-and-forth pacing (0 = none detected)."""
        if len(history) < self._pace_window:
            return 0.0
        recent_x = [h[0] for h in history[-self._pace_window:]]
        dxs = [recent_x[i + 1] - recent_x[i] for i in range(len(recent_x) - 1)]
        # Filter out sub-pixel noise
        significant = [d for d in dxs if abs(d) > 5]
        if len(significant) < 4:
            return 0.0
        reversals = sum(
            1
            for i in range(len(significant) - 1)
            if significant[i] * significant[i + 1] < 0
        )
        if reversals >= self._pace_reversals:
            return min(1.0, reversals / (self._pace_reversals * 2))
        return 0.0

    def _log_once(
        self,
        person_id: int,
        event_type: str,
        now: float,
        msg: str,
        *args: object,
        cooldown: float = 30.0,
    ) -> None:
        """Log *msg* at WARNING level at most once per *cooldown* seconds per (person, event)."""
        key = (person_id, event_type)
        if now - self._last_logged.get(key, 0.0) >= cooldown:
            logger.warning(msg, *args)
            self._last_logged[key] = now
