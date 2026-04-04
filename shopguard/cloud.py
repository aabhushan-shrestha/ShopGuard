"""Direct Supabase integration — alert metadata, JPEG frames, and heartbeats.

Authentication: Gmail via Supabase Auth (Google OAuth + PKCE flow).
On first launch the store owner is prompted to log in once via browser.
The session is saved to ``~/.shopguard/session.json`` and reused automatically
on subsequent launches (tokens are refreshed as needed).

All Supabase I/O runs in daemon threads so the detection loop is never blocked.

Required env vars:
    SUPABASE_URL       — project URL from Supabase settings > API
    SUPABASE_ANON_KEY  — anon (public) key  (RLS enforces per-user access)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from base64 import urlsafe_b64encode
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from shopguard.alerts import Alert
    from shopguard.config import AttrDict

logger = logging.getLogger(__name__)

_SESSION_FILE = Path.home() / ".shopguard" / "session.json"
_CALLBACK_PORT = 54321
_CALLBACK_URL = f"http://localhost:{_CALLBACK_PORT}/callback"


class SupabaseCloud:
    """Pushes alerts and heartbeats directly to Supabase.

    Disabled by default — set ``cloud.enabled: true`` in config.yaml and
    provide SUPABASE_URL + SUPABASE_ANON_KEY via env vars.

    On first run the store owner authenticates with Google once via browser.
    The session is saved locally; subsequent launches restore it automatically.
    """

    def __init__(self, cfg: AttrDict) -> None:
        ccfg = cfg.get("cloud", {})
        self._enabled: bool = bool(ccfg.get("enabled", False))
        self._heartbeat_interval: float = float(ccfg.get("heartbeat_interval", 60))
        self._bucket: str = ccfg.get("storage_bucket", "alert-frames")
        self._client = None
        self._url: str = ""
        self._user_id: str | None = None
        self._running = False
        self._heartbeat_thread: threading.Thread | None = None

        if not self._enabled:
            logger.info("SupabaseCloud: disabled — set cloud.enabled: true to activate")
            return

        try:
            from supabase import create_client  # noqa: PLC0415

            url: str = ccfg.get("url") or os.environ.get("SUPABASE_URL", "")
            key: str = ccfg.get("anon_key") or os.environ.get("SUPABASE_ANON_KEY", "")
            if not url or not key:
                logger.warning(
                    "SupabaseCloud: disabled — SUPABASE_URL and SUPABASE_ANON_KEY are required"
                )
                self._enabled = False
                return

            self._url = url
            self._client = create_client(url, key)

            # Restore saved session, or run interactive login
            if not self._restore_session():
                self._user_id = self._pkce_login()

            logger.info(
                "SupabaseCloud: connected (user_id=%s, bucket=%s)",
                self._user_id,
                self._bucket,
            )
        except ImportError:
            logger.warning("SupabaseCloud: disabled — run: pip install supabase")
            self._enabled = False
        except Exception:
            logger.exception("SupabaseCloud: init failed")
            self._enabled = False

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _restore_session(self) -> bool:
        """Load and validate a saved session. Returns True on success."""
        if not _SESSION_FILE.exists():
            return False
        try:
            data = json.loads(_SESSION_FILE.read_text())
            access_token: str = data["access_token"]
            refresh_token: str = data["refresh_token"]
            self._client.auth.set_session(access_token, refresh_token)  # type: ignore[union-attr]
            result = self._client.auth.get_user()  # type: ignore[union-attr]
            if result and result.user:
                self._user_id = result.user.id
                self._save_session()  # persist any refreshed tokens
                logger.info("SupabaseCloud: session restored (user_id=%s)", self._user_id)
                return True
        except Exception:
            logger.debug("SupabaseCloud: saved session invalid — will re-authenticate")
        return False

    def _save_session(self) -> None:
        """Persist current session tokens to disk."""
        try:
            session = self._client.auth.get_session()  # type: ignore[union-attr]
            if session is None:
                return
            _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            _SESSION_FILE.write_text(
                json.dumps(
                    {
                        "access_token": session.access_token,
                        "refresh_token": session.refresh_token,
                    }
                )
            )
        except Exception:
            logger.warning("SupabaseCloud: could not save session to disk")

    def _pkce_login(self) -> str:
        """Interactive Google OAuth PKCE login.

        Opens the user's browser to Google, starts a local HTTP server to
        catch the redirect, exchanges the code for a session, saves it, and
        returns the user's UUID.
        """
        # Build PKCE verifier + challenge
        code_verifier = secrets.token_urlsafe(96)
        digest = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = urlsafe_b64encode(digest).rstrip(b"=").decode()

        params = urllib.parse.urlencode(
            {
                "provider": "google",
                "redirect_to": _CALLBACK_URL,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        oauth_url = f"{self._url}/auth/v1/authorize?{params}"

        # Local HTTP server — waits for the OAuth redirect
        received: list[str] = []

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if "code" in qs:
                    received.append(qs["code"][0])
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(
                        b"<h2>ShopGuard: login successful!</h2>"
                        b"<p>You can close this tab and return to the terminal.</p>"
                    )
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"<h2>Login failed — please try again.</h2>")

            def log_message(self, *_args: object) -> None:
                pass  # suppress HTTP log noise

        server = HTTPServer(("localhost", _CALLBACK_PORT), _Handler)
        server.timeout = 120

        print(
            "\nShopGuard needs to authenticate with Google.\n"
            "Opening browser... if it doesn't open automatically, visit:\n"
            f"  {oauth_url}\n"
        )
        webbrowser.open(oauth_url)
        server.handle_request()  # blocks until redirect received (or 120 s timeout)
        server.server_close()

        if not received:
            raise RuntimeError("Google login timed out or was cancelled")

        # Exchange auth code for a Supabase session
        response = self._client.auth.exchange_code_for_session(  # type: ignore[union-attr]
            {"auth_code": received[0], "code_verifier": code_verifier}
        )
        if response is None or not hasattr(response, "user") or response.user is None:
            raise RuntimeError("Failed to exchange OAuth code for session")

        user_id: str = response.user.id
        self._save_session()
        logger.info(
            "SupabaseCloud: logged in as %s (user_id=%s)",
            getattr(response.user, "email", "?"),
            user_id,
        )
        return user_id

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
            "SupabaseCloud: heartbeat started (interval=%ss)", self._heartbeat_interval
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
                    "user_id": self._user_id,
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
            path = f"{self._user_id}/{ts}_{alert.alert_type}.jpg"
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
                    "user_id": self._user_id,
                    "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                on_conflict="user_id",
            ).execute()
            logger.debug("SupabaseCloud: heartbeat sent")
        except Exception:
            logger.exception("SupabaseCloud: heartbeat failed")
