"""Alert system with pluggable handlers and per-zone cooldowns."""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shopguard.config import AttrDict
    from shopguard.zones import ZoneStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Alert:
    """A single alert event."""
    zone_name: str
    alert_type: str  # "overcrowded" or "loitering"
    current_count: int
    max_allowed: int
    timestamp: float


# -- handlers -----------------------------------------------------------------

class ConsoleAlertHandler:
    """Logs alerts to the shopguard logger."""

    def handle(self, alert: Alert) -> None:
        logger.warning(
            "ALERT [%s] zone=%s  count=%d  max=%d",
            alert.alert_type, alert.zone_name,
            alert.current_count, alert.max_allowed,
        )


class WebhookAlertHandler:
    """POSTs alert JSON to a configured URL."""

    def __init__(self, url: str) -> None:
        self._url = url

    def handle(self, alert: Alert) -> None:
        payload = json.dumps({
            "zone_name": alert.zone_name,
            "alert_type": alert.alert_type,
            "current_count": alert.current_count,
            "max_allowed": alert.max_allowed,
            "timestamp": alert.timestamp,
        }).encode()
        req = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.debug("Webhook %s responded %s", self._url, resp.status)
        except Exception:
            logger.exception("Webhook POST to %s failed", self._url)


# -- manager ------------------------------------------------------------------

_HANDLER_REGISTRY: dict[str, type] = {
    "console": ConsoleAlertHandler,
    "webhook": WebhookAlertHandler,
}


class AlertManager:
    """Checks zone statuses and fires alerts respecting cooldowns."""

    def __init__(self, cfg: AttrDict) -> None:
        acfg = cfg.get("alerts", {})
        self._enabled: bool = acfg.get("enabled", True)
        self._cooldown: float = float(acfg.get("cooldown_seconds", 30))
        self._handlers: list[ConsoleAlertHandler | WebhookAlertHandler] = []
        self._last_fired: dict[str, float] = {}  # zone_name -> timestamp

        for h in acfg.get("handlers", []):
            if not h.get("enabled", True):
                continue
            htype = h["type"]
            if htype == "webhook":
                self._handlers.append(WebhookAlertHandler(url=h["url"]))
            elif htype in _HANDLER_REGISTRY:
                self._handlers.append(_HANDLER_REGISTRY[htype]())
            else:
                logger.warning("Unknown alert handler type: %s", htype)

        logger.info(
            "AlertManager: enabled=%s, cooldown=%ss, handlers=%d",
            self._enabled, self._cooldown, len(self._handlers),
        )

    def check_and_alert(self, zone_statuses: list[ZoneStatus]) -> list[Alert]:
        """Fire alerts for zones that exceed their limits. Returns fired alerts."""
        if not self._enabled:
            return []

        now = time.time()
        fired: list[Alert] = []
        for status in zone_statuses:
            if not status.is_over_limit:
                continue
            zone_name = status.zone.name
            last = self._last_fired.get(zone_name, 0.0)
            if now - last < self._cooldown:
                continue

            alert = Alert(
                zone_name=zone_name,
                alert_type="overcrowded",
                current_count=status.count,
                max_allowed=status.zone.max_occupancy,
                timestamp=now,
            )
            for handler in self._handlers:
                handler.handle(alert)
            self._last_fired[zone_name] = now
            fired.append(alert)

        return fired
