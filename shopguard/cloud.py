"""Direct Supabase integration — alert metadata, JPEG frames, and heartbeats.

The local agent calls this module instead of routing through a backend server.
All Supabase I/O runs in daemon threads so the detection loop is never blocked.

Required env vars (or equivalent ``cloud.*`` config keys):
    SUPABASE_URL   — project URL from Supabase settings > API
    SUPABASE_KEY   — anon (public) key  (RLS enforces access control)
    STORE_ID       — arbitrary stable identifier for this store PC
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from shopguard.alerts import Alert
    from shopguard.config import AttrDict

logger = logging.getLogger(__name__)


class SupabaseCloud:
    """Pushes alerts and heartbeats directly to Supabase.

    Disabled by default — set ``cloud.enabled: true`` in config.yaml and
    provide credentials via env vars or config keys.
    """

    def __init__(self, cfg: AttrDict) -> None:
        ccfg = cfg.get("cloud", {})
        self._enabled: bool = bool(ccfg.get("enabled", False))
        self._store_id: str = (
            ccfg.get("store_id") or os.environ.get("STORE_ID", "store_1")
        )
        self._heartbeat_interval: float = float(ccfg.get("heartbeat_interval", 60))
        self._bucket: str = ccfg.get("storage_bucket", "alert-frames")
        self._client = None
        self._running = False
        self._heartbeat_thread: threading.Thread | None = None

        if not self._enabled:
            logger.info("SupabaseCloud: disabled — set cloud.enabled: true to activate")
            return

        try:
            from supabase import create_client  # noqa: PLC0415

            url: str = ccfg.get("url") or os.environ.get("SUPABASE_URL", "")
            key: str = ccfg.get("anon_key") or os.environ.get("SUPABASE_KEY", "")
            if not url or not key:
                logger.warning(
                    "SupabaseCloud: disabled — SUPABASE_URL and SUPABASE_KEY are required"
                )
                self._enabled = False
                return

            self._client = create_client(url, key)
            logger.info(
                "SupabaseCloud: connected (store_id=%s, bucket=%s)",
                self._store_id,
                self._bucket,
            )
        except ImportError:
            logger.warning("SupabaseCloud: disabled — run: pip install supabase")
            self._enabled = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background heartbeat thread."""
        if not self._enabled:
            return
        self._running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="supabase-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()
        logger.info(
            "SupabaseCloud: heartbeat started (interval=%ss, store_id=%s)",
            self._heartbeat_interval,
            self._store_id,
        )

    def stop(self) -> None:
        """Signal the heartbeat thread to exit on its next wake."""
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def push_alert(
        self,
        alert: Alert,
        frame: np.ndarray | None,
        camera_source: int | str = 0,
    ) -> None:
        """Upload alert frame to Storage then insert metadata row.

        Runs in a daemon thread — never blocks the detection loop.
        """
        if not self._enabled:
            return
        threading.Thread(
            target=self._push_alert_sync,
            args=(alert, frame, camera_source),
            daemon=True,
            name="supabase-alert",
        ).start()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _push_alert_sync(
        self,
        alert: Alert,
        frame: np.ndarray | None,
        camera_source: int | str,
    ) -> None:
        image_url: str | None = None
        if frame is not None:
            image_url = self._upload_frame(frame, alert)

        try:
            self._client.table("alerts").insert(  # type: ignore[union-attr]
                {
                    "store_id": self._store_id,
                    "camera_index": str(camera_source),
                    "zone_name": alert.zone_name or "",
                    "timestamp": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(alert.timestamp)
                    ),
                    "image_url": image_url,
                }
            ).execute()
            logger.info(
                "SupabaseCloud: alert pushed (type=%s zone=%s image=%s)",
                alert.alert_type,
                alert.zone_name or "-",
                "yes" if image_url else "no",
            )
        except Exception:
            logger.exception("SupabaseCloud: failed to insert alert row")

    def _upload_frame(self, frame: np.ndarray, alert: Alert) -> str | None:
        """JPEG-encode *frame* and upload to Supabase Storage.

        Returns the public URL or ``None`` on failure.
        """
        try:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                return None
            ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(alert.timestamp))
            path = f"{self._store_id}/{ts}_{alert.alert_type}.jpg"
            self._client.storage.from_(self._bucket).upload(  # type: ignore[union-attr]
                path, buf.tobytes(), {"content-type": "image/jpeg"}
            )
            url: str = self._client.storage.from_(  # type: ignore[union-attr]
                self._bucket
            ).get_public_url(path)
            logger.debug("SupabaseCloud: frame uploaded → %s", url)
            return url
        except Exception:
            logger.exception("SupabaseCloud: frame upload failed")
            return None

    def _heartbeat_loop(self) -> None:
        while self._running:
            self._send_heartbeat()
            time.sleep(self._heartbeat_interval)

    def _send_heartbeat(self) -> None:
        try:
            self._client.table("heartbeats").upsert(  # type: ignore[union-attr]
                {
                    "store_id": self._store_id,
                    "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                on_conflict="store_id",
            ).execute()
            logger.debug("SupabaseCloud: heartbeat sent")
        except Exception:
            logger.exception("SupabaseCloud: heartbeat failed")
