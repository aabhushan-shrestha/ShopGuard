"""IoU-based person tracker that assigns stable IDs across frames."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from shopguard.detector import Detection

logger = logging.getLogger(__name__)


@dataclass
class Track:
    id: int
    detection: Detection
    last_seen: int


def _iou(a: Detection, b: Detection) -> float:
    """Compute intersection-over-union of two bounding boxes."""
    ix1 = max(a.x1, b.x1)
    iy1 = max(a.y1, b.y1)
    ix2 = min(a.x2, b.x2)
    iy2 = min(a.y2, b.y2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (a.x2 - a.x1) * (a.y2 - a.y1)
    area_b = (b.x2 - b.x1) * (b.y2 - b.y1)
    return inter / (area_a + area_b - inter)


class PersonTracker:
    """Assigns stable integer IDs to detected persons using greedy IoU matching."""

    def __init__(self, iou_threshold: float = 0.3, max_lost: int = 30) -> None:
        self._iou_threshold = iou_threshold
        self._max_lost = max_lost
        self._tracks: dict[int, Track] = {}
        self._next_id = 1
        self._frame = 0

    def update(self, detections: list[Detection]) -> list[tuple[int, Detection]]:
        """Match *detections* to existing tracks.

        Returns a list of (track_id, detection) for every detection in this frame.
        """
        self._frame += 1

        # Bootstrap: no existing tracks yet
        if not self._tracks:
            for det in detections:
                self._tracks[self._next_id] = Track(self._next_id, det, self._frame)
                self._next_id += 1
            return [(t.id, t.detection) for t in self._tracks.values()]

        # Build IoU scores between every live track and every new detection
        iou_pairs: list[tuple[float, int, int]] = []
        track_ids = list(self._tracks.keys())
        for tid in track_ids:
            for di, det in enumerate(detections):
                score = _iou(self._tracks[tid].detection, det)
                if score >= self._iou_threshold:
                    iou_pairs.append((score, tid, di))

        # Greedy assignment: highest IoU first
        iou_pairs.sort(reverse=True)
        matched_tracks: set[int] = set()
        matched_dets: set[int] = set()
        for _, tid, di in iou_pairs:
            if tid in matched_tracks or di in matched_dets:
                continue
            self._tracks[tid].detection = detections[di]
            self._tracks[tid].last_seen = self._frame
            matched_tracks.add(tid)
            matched_dets.add(di)

        # Spawn new tracks for unmatched detections
        for di, det in enumerate(detections):
            if di not in matched_dets:
                self._tracks[self._next_id] = Track(self._next_id, det, self._frame)
                logger.debug("New track %d at frame %d", self._next_id, self._frame)
                self._next_id += 1

        # Drop stale tracks (not seen for max_lost frames)
        stale = [
            tid for tid, t in self._tracks.items()
            if self._frame - t.last_seen > self._max_lost
        ]
        for tid in stale:
            logger.debug("Dropped stale track %d", tid)
            del self._tracks[tid]

        # Return only tracks confirmed this frame
        return [
            (t.id, t.detection)
            for t in self._tracks.values()
            if t.last_seen == self._frame
        ]
