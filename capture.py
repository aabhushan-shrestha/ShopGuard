import cv2
import time
from ultralytics import YOLO
from shopguard.detector import Detection
from shopguard.tracker import PersonTracker

model = YOLO("yolov8n.pt")
tracker = PersonTracker(iou_threshold=0.3, max_lost=30)

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

if not cap.isOpened():
    print("Error: Could not open camera at index 0")
    exit(1)

cv2.namedWindow("ShopGuard - Person Detection")
prev_time = time.time()

while True:
    if cv2.getWindowProperty("ShopGuard - Person Detection", cv2.WND_PROP_VISIBLE) < 1:
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

    cv2.imshow("ShopGuard - Person Detection", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord("q") or key == 27:  # q or Esc
        break

cap.release()
cv2.destroyAllWindows()
