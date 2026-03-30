"""Interactive zone editor — click to draw polygon zones on a frozen camera frame.

Usage:
    python zone_editor.py [--camera 0] [--zones config/zones.json]

Controls:
    SPACE       Freeze live feed and start editing
    LMB click   Add vertex to current polygon
    n / Enter   Finish zone (prompts for name/settings in terminal)
    u           Undo last vertex
    c           Clear current in-progress polygon
    d           Delete last completed zone
    s           Save zones to JSON and exit
    q / Esc     Exit without saving
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

WINDOW = "ShopGuard — Zone Editor"
_COLOR_NORMAL: tuple[int, int, int] = (0, 200, 0)
_COLOR_RESTRICTED: tuple[int, int, int] = (32, 32, 255)
_COLOR_CURRENT: tuple[int, int, int] = (0, 220, 255)

# Mutable editor state (module-level so mouse callback can reach it)
_current_pts: list[tuple[int, int]] = []
_completed: list[dict] = []


def _mouse_cb(event: int, x: int, y: int, _flags: int, _param: object) -> None:
    if event == cv2.EVENT_LBUTTONDOWN:
        _current_pts.append((x, y))


def _draw(frame: np.ndarray) -> np.ndarray:
    out = frame.copy()

    # Completed zones
    overlay = out.copy()
    for zone in _completed:
        pts = np.array(zone["points"], dtype=np.int32)
        color = _COLOR_RESTRICTED if zone.get("restricted") else _COLOR_NORMAL
        cv2.fillPoly(overlay, [pts], color)
        cv2.polylines(out, [pts], isClosed=True, color=color, thickness=2)
        top_idx = pts[:, 1].argmin()
        lx, ly = int(pts[top_idx][0]), int(pts[top_idx][1]) - 10
        tag = " [R]" if zone.get("restricted") else ""
        cv2.putText(out, zone["name"] + tag, (lx, ly),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
    cv2.addWeighted(overlay, 0.25, out, 0.75, 0, out)

    # In-progress polygon
    if _current_pts:
        for pt in _current_pts:
            cv2.circle(out, pt, 5, _COLOR_CURRENT, -1)
        if len(_current_pts) > 1:
            for i in range(len(_current_pts) - 1):
                cv2.line(out, _current_pts[i], _current_pts[i + 1], _COLOR_CURRENT, 2)
        if len(_current_pts) > 2:
            cv2.line(out, _current_pts[-1], _current_pts[0], _COLOR_CURRENT, 1)

    # HUD
    cv2.putText(out, f"Zones: {len(_completed)}  Vertices: {len(_current_pts)}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
    h = out.shape[0]
    for i, hint in enumerate([
        "LMB: add vertex | n: finish | u: undo | c: clear | d: del last | s: save | q: quit",
    ]):
        cv2.putText(out, hint, (10, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1, cv2.LINE_AA)

    return out


def _finish_zone() -> None:
    if len(_current_pts) < 3:
        logger.warning("Need at least 3 vertices (have %d) — keep clicking", len(_current_pts))
        return
    print(f"\n--- Finishing zone ({len(_current_pts)} vertices) ---")
    name = input("  Name [zone_N]: ").strip() or f"zone_{len(_completed) + 1}"
    restricted = input("  Restricted? (y/n) [n]: ").strip().lower() == "y"
    raw = input("  Max occupancy, 0=unlimited [0]: ").strip()
    max_occ = int(raw) if raw.isdigit() else 0
    color = list(_COLOR_RESTRICTED) if restricted else list(_COLOR_NORMAL)
    _completed.append({
        "name": name,
        "points": list(_current_pts),
        "max_occupancy": max_occ,
        "restricted": restricted,
        "color": color,
    })
    _current_pts.clear()
    logger.info("Zone %r added (%s)", name, "restricted" if restricted else "normal")


def _save(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"zones": _completed}, f, indent=2)
    logger.info("Saved %d zone(s) to %s", len(_completed), path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ShopGuard zone editor")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default 0)")
    parser.add_argument("--zones", default="config/zones.json", help="Path to zones JSON file")
    args = parser.parse_args(argv)

    zones_path = Path(args.zones)

    # Load existing zones
    if zones_path.exists():
        with open(zones_path, encoding="utf-8") as f:
            _completed.extend(json.load(f).get("zones", []))
        logger.info("Loaded %d existing zone(s) from %s", len(_completed), zones_path)

    # Open live feed, wait for SPACE to freeze
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        logger.error("Cannot open camera %d", args.camera)
        sys.exit(1)

    logger.info("Live feed — press SPACE to freeze and start editing, q to cancel")
    frozen: np.ndarray | None = None

    while True:
        ret, frame = cap.read()
        if not ret:
            logger.error("Failed to read frame")
            cap.release()
            sys.exit(1)
        cv2.imshow(WINDOW, frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord(" "):
            frozen = frame.copy()
            break
        if key in (ord("q"), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
            cap.release()
            cv2.destroyAllWindows()
            return

    cap.release()

    cv2.setMouseCallback(WINDOW, _mouse_cb)
    logger.info("Frame frozen. Click to add vertices. Press 'n' to finish each zone.")

    while True:
        if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
            break
        cv2.imshow(WINDOW, _draw(frozen))

        key = cv2.waitKey(30) & 0xFF

        if key in (ord("n"), 13):      # n or Enter
            _finish_zone()
        elif key == ord("u"):
            if _current_pts:
                _current_pts.pop()
                logger.info("Undo — %d vertices remain", len(_current_pts))
        elif key == ord("c"):
            _current_pts.clear()
            logger.info("Current polygon cleared")
        elif key == ord("d"):
            if _completed:
                removed = _completed.pop()
                logger.info("Deleted zone %r", removed["name"])
        elif key == ord("s"):
            _save(zones_path)
            break
        elif key in (ord("q"), 27):
            logger.info("Exiting without saving")
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
