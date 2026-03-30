# ShopGuard — Progress & Roadmap

> **What is ShopGuard?**
> A retail security system that detects suspicious behavior on camera and alerts staff in real time.

> **How to use this file:**
> Open this at the start of every session. Find the first unchecked box — that's where you pick up.

---

## Phase 1: Basic Person Detection ✅ COMPLETE

**Goal:** Get a live camera feed running with YOLOv8 detecting people in each frame.

**Files:**
- `capture.py` — main detection loop with webcam input
- `.gitignore` — project hygiene

**Tasks:**
- [x] Set up YOLOv8 with the nano model (`yolov8n.pt`)
- [x] Open webcam and read frames in a loop
- [x] Run person detection (class 0) on each frame
- [x] Draw bounding boxes and confidence scores
- [x] Display FPS and person count on screen
- [x] Quit cleanly with `q` key

---

## Phase 2: Person Tracking ✅ COMPLETE

**Goal:** Give each detected person a consistent ID so they can be followed across frames. This is the foundation for all behavior analysis later.

**Files:**
- `shopguard/tracker.py` — new file, tracking logic
- `capture.py` — integrate tracker into the detection loop

**Tasks:**
- [x] Create `shopguard/tracker.py` with a `PersonTracker` class
  - Use a simple algorithm (e.g. IoU-based matching or SORT) to associate detections across frames
  - Assign each person a unique ID on first appearance
  - Maintain a dictionary of active tracks (ID → bounding box, last seen frame)
  - Drop tracks that haven't been seen for N frames (stale timeout)
- [x] Update `capture.py` to import and use `PersonTracker`
  - After YOLO detection, pass bounding boxes to the tracker
  - Get back tracked IDs and matched boxes
  - Draw the person ID on screen next to each bounding box
- [x] Verify visually: same person keeps the same ID as they move around
- [x] Handle edge cases: people entering/leaving frame, brief occlusions

---

## Phase 3: Zone Definition ✅ COMPLETE

**Goal:** Let the user define regions of interest (e.g. exits, high-value aisles, restricted areas) so the system knows *where* things happen.

**Files:**
- `shopguard/zones.py` — zone creation and hit-testing
- `config/zones.json` — saved zone definitions
- `zone_editor.py` — interactive polygon zone editor
- `capture.py` — draw zones on screen, check if tracked persons are inside them

**Tasks:**
- [x] Design a simple zone format (list of polygons with labels)
- [x] Build a zone editor (click to define polygon corners on a frozen frame)
- [x] Save/load zones to `config/zones.json`
- [x] On each frame, check which zone each tracked person is in
- [x] Color-code zones on the display (green = normal, red = restricted)

---

## Phase 4: Behavior Analysis ⬅️ YOU ARE HERE

**Goal:** Use tracking history and zone data to flag suspicious patterns.

**Files:**
- `shopguard/behavior.py` — rule engine for suspicious behavior
- `shopguard/tracker.py` — extend with path history per person

**Tasks:**
- [ ] Store each person's position history (list of centroid coordinates over time)
- [ ] Detect loitering: person stays in the same zone for longer than a threshold
- [ ] Detect zone violations: person enters a restricted zone
- [ ] Detect unusual movement: pacing, repeated back-and-forth in the same area
- [ ] Each rule returns a suspicion event with type, person ID, confidence, and timestamp

---

## Phase 5: Alert System

**Goal:** When suspicious behavior is detected, notify staff immediately.

**Files:**
- `shopguard/alerts.py` — alert dispatcher
- `config/alerts.json` — alert settings (thresholds, notification channels)

**Tasks:**
- [ ] Define alert levels (info, warning, critical)
- [ ] On-screen alert overlay (flash border, show message)
- [ ] Sound alert (optional beep or chime)
- [ ] Log all alerts to `logs/alerts.log` with timestamps
- [ ] Webhook or message integration (Slack, email, SMS — pick one to start)
- [ ] Cooldown logic so the same event doesn't spam alerts

---

## Phase 6: Recording & Evidence

**Goal:** Automatically save video clips around suspicious events for later review.

**Files:**
- `shopguard/recorder.py` — clip saving logic
- `clips/` — output directory for saved clips

**Tasks:**
- [ ] Buffer the last N seconds of frames in memory (ring buffer)
- [ ] When an alert fires, save a clip: 10s before + 10s after the event
- [ ] Filename includes timestamp and event type
- [ ] Optional: save a snapshot image with bounding boxes drawn

---

## Phase 7: Dashboard & Review UI

**Goal:** A simple web interface to review alerts, watch clips, and manage zones.

**Files:**
- `dashboard/` — web app (Flask or FastAPI + simple HTML)
- `shopguard/api.py` — endpoints for the dashboard

**Tasks:**
- [ ] Live view of the camera feed in the browser
- [ ] Alert feed showing recent events
- [ ] Clip playback from saved recordings
- [ ] Zone editor in the browser (drag-and-drop polygons)
- [ ] Basic auth so only staff can access it
