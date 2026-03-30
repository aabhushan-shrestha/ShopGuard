"""Entry point — wires camera, detector, and display together."""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from shopguard import config as config_mod
from shopguard.alerts import AlertManager
from shopguard.behavior import BehaviorAnalyzer
from shopguard.camera import Camera
from shopguard.detector import Detector
from shopguard.display import Display
from shopguard.log import setup as setup_logging
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
    tcfg = cfg.tracker
    tracker = PersonTracker(
        iou_threshold=tcfg["iou_threshold"],
        max_lost=tcfg["max_lost"],
        max_history=tcfg.get("max_history", 300),
    )

    try:
        with Camera(cfg) as cam:
            frame_count = 0
            for frame in cam.frames():
                if not _running:
                    break

                detections = detector.detect(frame)
                tracked = tracker.update(detections)
                zone_statuses = zone_manager.check_occupancy(detections)
                behavior_events = behavior_analyzer.analyze(
                    tracker.active_tracks, zone_manager.zones
                )
                alert_manager.check_and_alert(zone_statuses, behavior_events)
                display.draw(frame, detections, zone_manager, zone_statuses, tracked, behavior_events)

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
        sys.exit(1)
    finally:
        display.cleanup()
        logger.info("ShopGuard stopped (processed %d frames)", frame_count)


if __name__ == "__main__":
    main()
