"""Interactive zone editor — click to draw polygon zones on a frozen camera frame.

Usage:
    python zone_editor.py [--camera 0] [--zones config/zones.json]

Controls:
    SPACE       Freeze live feed and start editing
    LMB click   Add vertex to current polygon
    n / Enter   Finish zone (opens on-screen input panel)
    u           Undo last vertex
    c           Clear current in-progress polygon
    d           Delete last completed zone
    s           Save zones to JSON and exit
    q / Esc     Exit without saving

On-screen input panel (appears after pressing n/Enter with ≥3 vertices):
    Type        Enter zone name / max occupancy digits
    Backspace   Delete last character
    y / n       Answer restricted prompt
    Enter       Confirm field and advance
    Esc         Cancel and return to drawing
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

# ── Editor state ────────────────────────────────────────────────────────────
_current_pts: list[tuple[int, int]] = []
_completed: list[dict] = []

# Input-panel state machine
# States: "drawing" | "name" | "restricted" | "maxocc"
_input_state: str = "drawing"
_input_buf: str = ""          # text buffer for name / maxocc fields
_partial: dict = {}           # accumulates name + restricted while collecting


def _mouse_cb(event: int, x: int, y: int, _flags: int, _param: object) -> None:
    if event == cv2.EVENT_LBUTTONDOWN and _input_state == "drawing":
        _current_pts.append((x, y))


# ── Drawing helpers ──────────────────────────────────────────────────────────

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
    cv2.putText(out,
                "LMB: add vertex | n: finish | u: undo | c: clear | d: del last | s: save | q: quit",
                (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1, cv2.LINE_AA)

    # On-screen input panel
    if _input_state != "drawing":
        _draw_input_panel(out)

    return out


def _draw_input_panel(out: np.ndarray) -> None:
    """Overlay a semi-transparent input panel in the centre of the frame."""
    h, w = out.shape[:2]
    bx, by, bw, bh = w // 4, h // 3, w // 2, h // 4

    # Semi-transparent dark background
    panel = out.copy()
    cv2.rectangle(panel, (bx, by), (bx + bw, by + bh), (20, 20, 20), -1)
    cv2.addWeighted(panel, 0.75, out, 0.25, 0, out)
    cv2.rectangle(out, (bx, by), (bx + bw, by + bh), (0, 200, 255), 2)

    # Title
    cv2.putText(out, "New Zone", (bx + 10, by + 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 200, 255), 2)

    # Prompt and live buffer
    if _input_state == "name":
        prompt = "Name (Enter to confirm):"
        value = _input_buf + "|"
    elif _input_state == "restricted":
        prompt = "Restricted zone? Press Y or N:"
        value = ""
    else:  # maxocc
        prompt = "Max occupancy, 0=unlimited (Enter):"
        value = _input_buf + "|"

    cv2.putText(out, prompt, (bx + 10, by + 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1, cv2.LINE_AA)
    cv2.putText(out, value, (bx + 10, by + 85),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 100), 2)

    # Hint
    cv2.putText(out, "Esc: cancel", (bx + 10, by + bh - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (160, 160, 160), 1, cv2.LINE_AA)


# ── State-machine key handling ───────────────────────────────────────────────

def _handle_input_key(key: int) -> None:
    """Process a keypress while the input panel is active."""
    global _input_state, _input_buf, _partial

    if key == 27:  # Esc — cancel
        _input_state = "drawing"
        _input_buf = ""
        _partial = {}
        logger.info("Zone input cancelled")
        return

    if _input_state == "name":
        if key == 13:  # Enter — confirm name
            name = _input_buf.strip() or f"zone_{len(_completed) + 1}"
            _partial["name"] = name
            _input_buf = ""
            _input_state = "restricted"
            logger.debug("Zone name set to %r", name)
        elif key == 8:  # Backspace
            _input_buf = _input_buf[:-1]
        elif 32 <= key <= 126:  # printable ASCII
            _input_buf += chr(key)

    elif _input_state == "restricted":
        if key in (ord("y"), ord("Y")):
            _partial["restricted"] = True
            _input_state = "maxocc"
        elif key in (ord("n"), ord("N"), 13):
            _partial["restricted"] = False
            _input_state = "maxocc"

    elif _input_state == "maxocc":
        if key == 13:  # Enter — confirm and finalise zone
            raw = _input_buf.strip()
            max_occ = int(raw) if raw.isdigit() else 0
            _finalise_zone(
                name=_partial["name"],
                restricted=_partial["restricted"],
                max_occ=max_occ,
            )
            _input_buf = ""
            _partial = {}
            _input_state = "drawing"
        elif key == 8:
            _input_buf = _input_buf[:-1]
        elif ord("0") <= key <= ord("9"):
            _input_buf += chr(key)


def _finalise_zone(name: str, restricted: bool, max_occ: int) -> None:
    color = list(_COLOR_RESTRICTED) if restricted else list(_COLOR_NORMAL)
    _completed.append({
        "name": name,
        "points": list(_current_pts),
        "max_occupancy": max_occ,
        "restricted": restricted,
        "color": color,
    })
    _current_pts.clear()
    logger.info("Zone %r added (%s, max_occ=%d)",
                name, "restricted" if restricted else "normal", max_occ)


def _begin_finish_zone() -> None:
    """Called when user presses n/Enter in drawing mode."""
    global _input_state, _input_buf
    if len(_current_pts) < 3:
        logger.warning("Need at least 3 vertices (have %d) — keep clicking", len(_current_pts))
        return
    _input_buf = ""
    _input_state = "name"


# ── Persistence ──────────────────────────────────────────────────────────────

def _save(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"zones": _completed}, f, indent=2)
    logger.info("Saved %d zone(s) to %s", len(_completed), path)


# ── Entry point ──────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ShopGuard zone editor")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default 0)")
    parser.add_argument("--zones", default="config/zones.json", help="Path to zones JSON file")
    args = parser.parse_args(argv)

    zones_path = Path(args.zones)

    if zones_path.exists():
        with open(zones_path, encoding="utf-8") as f:
            _completed.extend(json.load(f).get("zones", []))
        logger.info("Loaded %d existing zone(s) from %s", len(_completed), zones_path)

    # ── Live-feed phase: wait for SPACE to freeze ────────────────────────────
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        logger.error("Cannot open camera %d", args.camera)
        sys.exit(1)

    logger.info("Live feed — press SPACE to freeze and start editing, q to cancel")

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

    # ── Editing phase ────────────────────────────────────────────────────────
    cv2.setMouseCallback(WINDOW, _mouse_cb)
    logger.info("Frame frozen. Click to add vertices. Press 'n' to finish each zone.")

    while True:
        if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
            break

        cv2.imshow(WINDOW, _draw(frozen))
        key = cv2.waitKey(30) & 0xFF

        if _input_state != "drawing":
            _handle_input_key(key)
            continue

        # Normal drawing-mode keys
        if key in (ord("n"), 13):        # n or Enter → begin zone finish
            _begin_finish_zone()
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
