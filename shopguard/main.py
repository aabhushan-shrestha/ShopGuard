"""Entry point — wires camera, detector, and display together."""

from __future__ import annotations

import argparse
import logging
import signal

from shopguard import config as config_mod
from shopguard.alerts import AlertManager
from shopguard.api import DashboardState, start_dashboard
from shopguard.behavior import BehaviorAnalyzer
from shopguard.camera import Camera
from shopguard.detector import Detector
from shopguard.display import Display
from shopguard.log import setup as setup_logging
from shopguard.recorder import ClipRecorder
from shopguard.tracker import PersonTracker
from shopguard.zones import ZoneManager

logger = logging.getLogger(__name__)

_running = True


def _shutdown(signum: int, _frame: object) -> None:
    global _running
    logger.info("Received signal %s, shutting down", signal.Signals(signum).name)
    _running = False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ShopGuard person detection")
    parser.add_argument(
        "--config", default="config.yaml", help="Path to YAML config file"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    global _running
    _running = True

    args = parse_args(argv)
    cfg = config_mod.load(args.config)
    setup_logging(cfg)

    logger.info("ShopGuard starting")

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    detector = Detector(cfg)
    display = Display(cfg)
    zone_manager = ZoneManager(cfg)
    alert_manager = AlertManager(cfg)
    behavior_analyzer = BehaviorAnalyzer(cfg)
    recorder = ClipRecorder(cfg)

    dashboard_cfg = cfg.get("dashboard", {})
    dashboard_state = DashboardState(max_alerts=dashboard_cfg.get("max_alerts", 100))
    if dashboard_cfg.get("enabled", True):
        start_dashboard(dashboard_state, cfg)
    tcfg = cfg.tracker
    tracker = PersonTracker(
        iou_threshold=tcfg["iou_threshold"],
        max_lost=tcfg["max_lost"],
        max_history=tcfg.get("max_history", 300),
    )

    frame_count = 0
    try:
        with Camera(cfg) as cam:
            for frame in cam.frames():
                if not _running:
                    break

                detections = detector.detect(frame)
                tracked = tracker.update(detections)
                zone_statuses = zone_manager.check_occupancy(detections)
                behavior_events = behavior_analyzer.analyze(
                    tracker.active_tracks, zone_manager.zones
                )
                fired_alerts = alert_manager.check_and_alert(zone_statuses, behavior_events)
                display.draw(frame, detections, zone_manager, zone_statuses, tracked, behavior_events)

                # Push annotated frame (after draw), trigger clips, update dashboard
                recorder.push_frame(frame)
                for alert in fired_alerts:
                    recorder.trigger(alert)
                    dashboard_state.add_alert(alert)
                dashboard_state.update_frame(frame)

                if not display.show(frame):
                    break

                frame_count += 1
                if frame_count % 300 == 0:
                    logger.info(
                        "Heartbeat: %d frames processed, %d persons in last frame",
                        frame_count, len(detections),
                    )
    except RuntimeError as exc:
        logger.error("Fatal: %s", exc)
    finally:
        display.cleanup()
        logger.info("ShopGuard stopped (processed %d frames)", frame_count)


if __name__ == "__main__":
    main()
