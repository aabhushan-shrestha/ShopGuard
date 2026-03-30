import json
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from shopguard.detector import Detection
from shopguard.tracker import PersonTracker
from shopguard.zones import ZoneManager, _zones_from_list

WINDOW = "ShopGuard - Person Detection"
ZONES_JSON = Path("config/zones.json")

model = YOLO("yolov8n.pt")
tracker = PersonTracker(iou_threshold=0.3, max_lost=30)

# Load zones from JSON if available, otherwise empty
_zone_list: list[dict] = []
if ZONES_JSON.exists():
    with open(ZONES_JSON, encoding="utf-8") as _f:
        _zone_list = json.load(_f).get("zones", [])
zones = _zones_from_list(_zone_list)

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

if not cap.isOpened():
    print("Error: Could not open camera at index 0")
    exit(1)

cv2.namedWindow(WINDOW)
prev_time = time.time()

while True:
    if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
        break

    ret, frame = cap.read()
    if not ret:
        print("Error: Failed to read frame")
        break

    results = model(frame, classes=[0], verbose=False)  # class 0 = person

    detections = []
    for box in results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        conf = float(box.conf[0])
        detections.append(Detection(x1, y1, x2, y2, conf))

    tracked = tracker.update(detections)

    # Zone overlay
    if zones:
        overlay = frame.copy()
        for zone in zones:
            pts = zone.contour
            color = zone.display_color()
            cv2.fillPoly(overlay, [pts], color)
            cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)
        cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)
        for zone in zones:
            inside = sum(
                1 for det in detections
                if cv2.pointPolygonTest(zone.contour, (float(det.center[0]), float(det.center[1])), False) >= 0
            )
            over = zone.max_occupancy > 0 and inside > zone.max_occupancy
            color = zone.display_color(over)
            pts = zone.contour
            top_idx = pts[:, 1].argmin()
            lx, ly = int(pts[top_idx][0]), int(pts[top_idx][1]) - 10
            label = f"{zone.name}: {inside}/{zone.max_occupancy}" if zone.max_occupancy > 0 else f"{zone.name}: {inside}"
            cv2.putText(frame, label, (lx, ly), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    for tid, det in tracked:
        cv2.rectangle(frame, (det.x1, det.y1), (det.x2, det.y2), (0, 255, 0), 2)
        cv2.putText(frame, f"ID {tid} {det.confidence:.2f}", (det.x1, det.y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    curr_time = time.time()
    fps = 1.0 / (curr_time - prev_time)
    prev_time = curr_time

    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)
    cv2.putText(frame, f"Persons: {len(tracked)}", (10, 65),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)

    cv2.imshow(WINDOW, frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord("q") or key == 27:  # q or Esc
        break

cap.release()
cv2.destroyAllWindows()
