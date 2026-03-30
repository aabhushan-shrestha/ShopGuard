"""Alert system: levels, handlers (console, file, sound, telegram, webhook), cooldowns."""

from __future__ import annotations

import enum
import json
import logging
import os
import time
import urllib.request
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shopguard.behavior import SuspicionEvent
    from shopguard.config import AttrDict
    from shopguard.zones import ZoneStatus

logger = logging.getLogger(__name__)


class AlertLevel(enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class Alert:
    """A single fired alert."""
    level: AlertLevel
    alert_type: str        # "overcrowded" | "zone_violation" | "loitering" | "pacing"
    message: str
    timestamp: float
    zone_name: str | None = None
    person_id: int | None = None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

class ConsoleAlertHandler:
    """Logs alerts via the shopguard logger."""

    def handle(self, alert: Alert) -> None:
        logger.warning(
            "ALERT [%s] %s: %s",
            alert.level.value.upper(), alert.alert_type, alert.message,
        )


class FileAlertHandler:
    """Appends one line per alert to a dedicated alerts log file."""

    def __init__(self, path: str = "logs/alerts.log") -> None:
        log_path = Path(path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._alert_logger = logging.getLogger("shopguard.alerts_file")
        self._alert_logger.propagate = False
        if not self._alert_logger.handlers:
            fh = RotatingFileHandler(
                log_path, maxBytes=5_242_880, backupCount=3, encoding="utf-8",
            )
            fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
            fh.setLevel(logging.DEBUG)
            self._alert_logger.addHandler(fh)
        self._alert_logger.setLevel(logging.DEBUG)

    def handle(self, alert: Alert) -> None:
        self._alert_logger.warning(
            "[%s] type=%s  zone=%s  person=%s  msg=%s",
            alert.level.value.upper(), alert.alert_type,
            alert.zone_name or "-",
            alert.person_id if alert.person_id is not None else "-",
            alert.message,
        )


class SoundAlertHandler:
    """Plays a short beep. Uses winsound on Windows, falls back to terminal bell."""

    def __init__(self, frequency: int = 1000, duration_ms: int = 300) -> None:
        self._freq = frequency
        self._dur = duration_ms
        try:
            import winsound as _ws  # noqa: PLC0415
            self._winsound = _ws
        except ImportError:
            self._winsound = None

    def handle(self, alert: Alert) -> None:
        if self._winsound is not None:
            try:
                self._winsound.Beep(self._freq, self._dur)
                return
            except RuntimeError:
                pass
        print("\a", end="", flush=True)


class TelegramAlertHandler:
    """Sends alert messages via the Telegram Bot API."""

    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token
        self._chat_id = chat_id

    def handle(self, alert: Alert) -> None:
        emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(
            alert.level.value, ""
        )
        text = (
            f"{emoji} [ShopGuard] {alert.level.value.upper()}\n"
            f"Type: {alert.alert_type}\n"
            f"{alert.message}"
        )
        payload = json.dumps({"chat_id": self._chat_id, "text": text}).encode()
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception:
            logger.exception("Telegram alert failed")


class WebhookAlertHandler:
    """POSTs alert JSON to a configured URL."""

    def __init__(self, url: str) -> None:
        self._url = url

    def handle(self, alert: Alert) -> None:
        payload = json.dumps({
            "level": alert.level.value,
            "alert_type": alert.alert_type,
            "message": alert.message,
            "zone_name": alert.zone_name,
            "person_id": alert.person_id,
            "timestamp": alert.timestamp,
        }).encode()
        req = urllib.request.Request(
            self._url, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.debug("Webhook %s responded %s", self._url, resp.status)
        except Exception:
            logger.exception("Webhook POST to %s failed", self._url)


# ---------------------------------------------------------------------------
# Level mapping for behavior events
# ---------------------------------------------------------------------------

_BEHAVIOR_LEVELS: dict[str, AlertLevel] = {
    "zone_violation": AlertLevel.CRITICAL,
    "loitering": AlertLevel.WARNING,
    "pacing": AlertLevel.INFO,
}

AnyHandler = (
    ConsoleAlertHandler
    | FileAlertHandler
    | SoundAlertHandler
    | TelegramAlertHandler
    | WebhookAlertHandler
)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class AlertManager:
    """Dispatches alerts for zone overcrowding and behavior events with cooldown logic."""

    def __init__(self, cfg: AttrDict) -> None:
        acfg = cfg.get("alerts", {})
        self._enabled: bool = acfg.get("enabled", True)
        self._cooldown: float = float(acfg.get("cooldown_seconds", 30))
        self._handlers: list[AnyHandler] = []  # type: ignore[valid-type]
        self._last_zone_fired: dict[str, float] = {}
        self._last_behavior_fired: dict[tuple[int, str], float] = {}

        for h in acfg.get("handlers", []):
            if not h.get("enabled", True):
                continue
            htype = h["type"]
            if htype == "console":
                self._handlers.append(ConsoleAlertHandler())
            elif htype == "file":
                self._handlers.append(FileAlertHandler(h.get("path", "logs/alerts.log")))
            elif htype == "sound":
                self._handlers.append(SoundAlertHandler(
                    frequency=h.get("frequency", 1000),
                    duration_ms=h.get("duration_ms", 300),
                ))
            elif htype == "telegram":
                token = h.get("token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
                chat_id = h.get("chat_id") or os.environ.get("TELEGRAM_CHAT_ID", "")
                if token and chat_id:
                    self._handlers.append(TelegramAlertHandler(token, chat_id))
                else:
                    logger.warning(
                        "Telegram handler skipped: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
                    )
            elif htype == "webhook":
                self._handlers.append(WebhookAlertHandler(url=h["url"]))
            else:
                logger.warning("Unknown alert handler type: %s", htype)

        logger.info(
            "AlertManager: enabled=%s, cooldown=%ss, handlers=%d",
            self._enabled, self._cooldown, len(self._handlers),
        )

    def check_and_alert(
        self,
        zone_statuses: list[ZoneStatus],
        behavior_events: list[SuspicionEvent] | None = None,
    ) -> list[Alert]:
        """Fire alerts for zone overcrowding and behavior events. Returns fired alerts."""
        if not self._enabled:
            return []

        now = time.time()
        fired: list[Alert] = []

        # Zone overcrowding
        for status in zone_statuses:
            if not status.is_over_limit:
                continue
            zone_name = status.zone.name
            if now - self._last_zone_fired.get(zone_name, 0.0) < self._cooldown:
                continue
            alert = Alert(
                level=AlertLevel.WARNING,
                alert_type="overcrowded",
                message=(
                    f"Zone '{zone_name}' has {status.count}/{status.zone.max_occupancy} persons"
                ),
                timestamp=now,
                zone_name=zone_name,
            )
            self._dispatch(alert)
            self._last_zone_fired[zone_name] = now
            fired.append(alert)

        # Behavior events
        for ev in (behavior_events or []):
            key = (ev.person_id, ev.type)
            if now - self._last_behavior_fired.get(key, 0.0) < self._cooldown:
                continue
            level = _BEHAVIOR_LEVELS.get(ev.type, AlertLevel.WARNING)
            zone_info = f" in zone '{ev.zone_name}'" if ev.zone_name else ""
            alert = Alert(
                level=level,
                alert_type=ev.type,
                message=(
                    f"Person {ev.person_id} — {ev.type}{zone_info} (conf={ev.confidence:.2f})"
                ),
                timestamp=now,
                zone_name=ev.zone_name,
                person_id=ev.person_id,
            )
            self._dispatch(alert)
            self._last_behavior_fired[key] = now
            fired.append(alert)

        return fired

    def _dispatch(self, alert: Alert) -> None:
        for handler in self._handlers:
            try:
                handler.handle(alert)
            except Exception:
                logger.exception("Alert handler %s failed", type(handler).__name__)
