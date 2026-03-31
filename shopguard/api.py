"""Flask dashboard: live feed, alert log, clip browser, zone editor."""

from __future__ import annotations

import collections
import json
import logging
import os
import threading
import time
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
from flask import Flask, Response, abort, jsonify, render_template, request, send_file

from shopguard.zones import JSON_PATH as ZONES_JSON_PATH

if TYPE_CHECKING:
    from shopguard.alerts import Alert
    from shopguard.camera import Camera
    from shopguard.config import AttrDict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

class DashboardState:
    """Thread-safe state shared between the detection loop and the Flask app."""

    def __init__(self, max_alerts: int = 100) -> None:
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._alerts: collections.deque[dict[str, Any]] = collections.deque(maxlen=max_alerts)
        self._camera: Camera | None = None

    def update_frame(self, frame: np.ndarray) -> None:
        with self._lock:
            self._frame = frame.copy()

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def add_alert(self, alert: Alert) -> None:
        with self._lock:
            self._alerts.append({
                "level": alert.level.value,
                "alert_type": alert.alert_type,
                "message": alert.message,
                "timestamp": alert.timestamp,
                "zone_name": alert.zone_name,
                "person_id": alert.person_id,
            })

    def get_alerts(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(self._alerts))

    def set_camera(self, cam: Camera) -> None:
        with self._lock:
            self._camera = cam

    @property
    def camera(self) -> Camera | None:
        with self._lock:
            return self._camera


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(state: DashboardState, cfg: AttrDict, zone_manager: Any = None) -> Flask:
    """Build and return the Flask application."""
    dcfg = cfg.get("dashboard", {})
    auth_cfg = dcfg.get("auth", {})
    _username: str = auth_cfg.get("username", "admin")
    _password: str = auth_cfg.get("password", "shopguard")
    clips_dir = Path(cfg.get("recorder", {}).get("clips_dir", "clips"))

    template_dir = Path(__file__).parent.parent / "dashboard" / "templates"
    app = Flask(__name__, template_folder=str(template_dir))

    # Silence Werkzeug request logs (keep warnings+)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    # -- auth helper ----------------------------------------------------------

    def _require_auth(f):  # type: ignore[no-untyped-def]
        @wraps(f)
        def decorated(*args: Any, **kwargs: Any) -> Any:
            auth = request.authorization
            if not auth or auth.username != _username or auth.password != _password:
                return Response(
                    "Authentication required.",
                    401,
                    {"WWW-Authenticate": 'Basic realm="ShopGuard"'},
                )
            return f(*args, **kwargs)
        return decorated

    # -- MJPEG generator ------------------------------------------------------

    def _mjpeg_stream():  # type: ignore[return]
        while True:
            frame = state.get_frame()
            if frame is None:
                time.sleep(0.05)
                continue
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not ok:
                time.sleep(0.05)
                continue
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                + buf.tobytes()
                + b"\r\n"
            )
            time.sleep(1 / 25)  # cap browser stream at ~25 fps

    # -- routes ---------------------------------------------------------------

    @app.route("/")
    @_require_auth
    def index() -> str:
        return render_template("index.html")

    @app.route("/video_feed")
    @_require_auth
    def video_feed() -> Response:
        return Response(
            _mjpeg_stream(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/api/frame")
    @_require_auth
    def api_frame() -> Response:
        """Return the latest frame as a JPEG snapshot (used by zone editor)."""
        frame = state.get_frame()
        if frame is None:
            abort(503)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            abort(500)
        return Response(buf.tobytes(), mimetype="image/jpeg")

    @app.route("/api/alerts")
    @_require_auth
    def api_alerts() -> Response:
        return jsonify(state.get_alerts())

    @app.route("/api/clips")
    @_require_auth
    def api_clips() -> Response:
        if not clips_dir.exists():
            return jsonify([])
        clips = []
        for p in sorted(clips_dir.glob("*.mp4"), reverse=True):
            stem = p.stem
            snapshot = clips_dir / f"{stem}_snapshot.jpg"
            clips.append({
                "name": p.name,
                "stem": stem,
                "has_snapshot": snapshot.exists(),
            })
        return jsonify(clips)

    @app.route("/clips/<path:filename>")
    @_require_auth
    def serve_clip(filename: str) -> Response:
        base = clips_dir.resolve()
        path = (clips_dir / filename).resolve()
        # Prevent path traversal
        try:
            path.relative_to(base)
        except ValueError:
            abort(403)
        if not path.is_file():
            abort(404)
        return send_file(str(path))

    @app.route("/api/zones", methods=["GET"])
    @_require_auth
    def api_zones_get() -> Response:
        if ZONES_JSON_PATH.exists():
            data = json.loads(ZONES_JSON_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return jsonify(data)
            return jsonify(data.get("zones", []))
        return jsonify([])

    @app.route("/api/zones", methods=["POST"])
    @_require_auth
    def api_zones_post() -> Response:
        data = request.get_json(force=True)
        if not isinstance(data, list):
            abort(400)
        ZONES_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        ZONES_JSON_PATH.write_text(json.dumps({"zones": data}, indent=2), encoding="utf-8")
        logger.info("Dashboard: zones updated (%d zones)", len(data))
        if zone_manager is not None:
            zone_manager.reload()
        return jsonify({"saved": len(data)})

    @app.route("/api/cameras", methods=["GET"])
    @_require_auth
    def api_cameras() -> Response:
        _labels = {0: "iVCam / Default", 1: "Built-in Webcam"}
        found = []
        for i in range(5):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                found.append({"index": i, "label": _labels.get(i, f"Camera {i}")})
            cap.release()
        return jsonify(found)

    @app.route("/api/camera/switch", methods=["POST"])
    @_require_auth
    def api_camera_switch() -> Response:
        body = request.get_json(force=True)
        source = body.get("source")
        if not isinstance(source, int):
            abort(400)
        cam = state.camera
        if cam is None:
            return jsonify({"ok": False, "error": "Camera not initialised"}), 500
        try:
            cam.switch_source(source)
            return jsonify({"ok": True, "source": source})
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    return app


# ---------------------------------------------------------------------------
# Thread launcher
# ---------------------------------------------------------------------------

def start_dashboard(state: DashboardState, cfg: AttrDict, zone_manager: Any = None) -> threading.Thread:
    """Start the Flask dashboard in a background daemon thread."""
    dcfg = cfg.get("dashboard", {})
    host: str = dcfg.get("host", "0.0.0.0")
    port: int = int(dcfg.get("port", 8080))
    app = create_app(state, cfg, zone_manager)

    def _run() -> None:
        logger.info("Dashboard: http://%s:%d  (user: %s)", host, port,
                    dcfg.get("auth", {}).get("username", "admin"))
        app.run(host=host, port=port, threaded=True, use_reloader=False)

    thread = threading.Thread(target=_run, name="dashboard", daemon=True)
    thread.start()
    return thread
