# ShopGuard — Progress & Roadmap

> **What is ShopGuard?**
> A retail security system that detects suspicious behavior on camera and alerts staff in real time.

> **How to use this file:**
> Open this at the start of every session. Find the first unchecked box — that's where you pick up.

---

## Architecture (current)

```
Store PC                          Cloud (Supabase)          Dashboard (Vercel)
─────────────────────────         ──────────────────────    ──────────────────
shopguard/ local agent            alerts table              dashboard-web/
  ├─ camera.py  (RTSP/USB)   ──►  heartbeats table     ◄──  Next.js app
  ├─ detector.py (YOLOv8)        alert-frames bucket        reads Supabase
  ├─ tracker.py                                              directly
  ├─ zones.py                RTSP credentials stay local,
  ├─ behavior.py             only metadata + JPEG leaves
  ├─ alerts.py               the store PC
  ├─ recorder.py (local MP4)
  ├─ cloud.py ──────────────►  Supabase SDK (direct)
  ├─ api.py  (local Flask dashboard, zone editor)
  └─ main.py
```

**What stays local:** RTSP stream, YOLOv8 detection, zone monitoring, clip recording, Flask zone editor.  
**What goes to Supabase:** alert metadata + JPEG frame (on alert), heartbeat every 60 s.  
**Dashboard:** Next.js on Vercel reads Supabase directly — no backend server.

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

## Phase 4: Behavior Analysis ✅ COMPLETE

**Goal:** Use tracking history and zone data to flag suspicious patterns.

**Files:**
- `shopguard/behavior.py` — rule engine for suspicious behavior
- `shopguard/tracker.py` — extend with path history per person

**Tasks:**
- [x] Store each person's position history (list of centroid coordinates over time)
- [x] Detect loitering: person stays in the same zone for longer than a threshold
- [x] Detect zone violations: person enters a restricted zone
- [x] Detect unusual movement: pacing, repeated back-and-forth in the same area
- [x] Each rule returns a suspicion event with type, person ID, confidence, and timestamp

---

## Phase 5: Alert System ✅ COMPLETE

**Goal:** When suspicious behavior is detected, notify staff immediately.

**Files:**
- `shopguard/alerts.py` — alert dispatcher with pluggable handlers
- `config.yaml` — alert settings (cooldown, handlers, Telegram config)

**Tasks:**
- [x] Define alert levels (info, warning, critical)
- [x] On-screen alert overlay (flash border, show message)
- [x] Sound alert (optional beep or chime)
- [x] Log all alerts to `logs/alerts.log` with timestamps
- [x] Webhook or message integration (Slack, email, SMS — pick one to start)
- [x] Cooldown logic so the same event doesn't spam alerts

---

## Phase 6: Recording & Evidence ✅ COMPLETE

**Goal:** Automatically save video clips around suspicious events for later review.

**Files:**
- `shopguard/recorder.py` — clip saving logic
- `clips/` — output directory for saved clips (gitignored)

**Tasks:**
- [x] Buffer the last N seconds of frames in memory (ring buffer)
- [x] When an alert fires, save a clip: 10s before + 10s after the event
- [x] Filename includes timestamp and event type
- [x] Optional: save a snapshot image with bounding boxes drawn

---

## Phase 7: Local Dashboard ✅ COMPLETE

**Goal:** A local web interface on the store PC to review alerts, watch clips, and manage zones.

**Files:**
- `shopguard/api.py` — Flask app factory, DashboardState, all routes
- `dashboard/templates/index.html` — single-page dashboard UI

**Tasks:**
- [x] Live view of the camera feed in the browser
- [x] Alert feed showing recent events
- [x] Clip playback from saved recordings
- [x] Zone editor in the browser (click-to-draw polygons)
- [x] Basic auth so only staff can access it

---

## Phase A: RTSP Camera Connectivity ✅ COMPLETE

**Goal:** ShopGuard works with any camera — phones, CCTVs, IP cameras — without requiring iVCam or USB connection.

**Files:**
- `shopguard/camera.py` — updated to handle int (USB) and string (RTSP) sources
- `shopguard/api.py` — RTSP camera CRUD endpoints, updated camera listing/switching
- `shopguard/zones.py` — zone paths for RTSP cameras via URL hash
- `dashboard/templates/index.html` — "Add RTSP Camera" form in camera selector
- `config.yaml` — source field now accepts int or RTSP URL string
- `config/cameras.json` — persisted RTSP camera list (created at runtime)

**Tasks:**
- [x] Accept RTSP URLs as camera source in config.yaml
- [x] Update camera.py to handle both integer index (USB) and string URL (RTSP) sources
- [x] Add RTSP camera management UI in dashboard camera selector
- [x] Add "Add RTSP Camera" form in dashboard (name + URL fields)
- [x] Persist RTSP camera list to config/cameras.json per store
- [x] Update PROGRESS.md

---

## Phase B: Cloud API Foundation ~~SUPERSEDED~~

> **Superseded by Phase C.** The FastAPI/Railway server has been removed.
> The local agent now talks directly to Supabase — no middleman.
> The `cloud-api/` directory has been deleted from the repo.

---

## Phase C: Direct Supabase Integration ✅ COMPLETE

**Goal:** Local agent pushes alert metadata and JPEG frames directly to Supabase.
No FastAPI server, no Railway, no Render. Supabase is the only cloud dependency.

**Files:**
- `shopguard/cloud.py` — SupabaseCloud: heartbeat thread, alert upload, frame upload
- `shopguard/main.py` — wires in SupabaseCloud (start/stop, push_alert on each fired alert)
- `supabase/schema.sql` — minimal schema: alerts + heartbeats tables + RLS policies
- `config.yaml` — new `cloud:` section (disabled by default)
- `.env.example` — SUPABASE_URL, SUPABASE_KEY, STORE_ID
- `requirements.txt` — added supabase>=2.0.0, python-dotenv>=1.0.0

**Tasks:**
- [x] Create `shopguard/cloud.py` with `SupabaseCloud` class
- [x] Heartbeat: background thread upserts `heartbeats` row every 60 s
- [x] Alert: on each fired alert, JPEG-encode the current frame and upload to `alert-frames` bucket
- [x] Alert: insert row to `alerts` table with store_id, camera_index, zone_name, timestamp, image_url
- [x] All Supabase I/O in daemon threads — detection loop never blocked
- [x] Disabled by default; enabled via `cloud.enabled: true` + env vars
- [x] RLS policies: anon key can insert (agent) and select (dashboard)
- [x] RTSP credentials stay in local .env only — never sent to cloud
- [x] Delete `cloud-api/` (FastAPI/Railway server)
- [x] Update PROGRESS.md

---

## Phase D: Vercel Dashboard ✅ COMPLETE

**Goal:** A Next.js frontend on Vercel that reads alerts and heartbeats directly from Supabase.

**Files:**
- `dashboard-web/app/page.tsx` — server component: alert feed + store online/offline status
- `dashboard-web/app/layout.tsx` — root layout
- `dashboard-web/lib/supabase.ts` — Supabase client + shared types + isOnline helper
- `dashboard-web/package.json` — Next.js 15, @supabase/supabase-js
- `dashboard-web/vercel.json` — Vercel deployment config
- `dashboard-web/.env.local.example` — NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY

**Tasks:**
- [x] Scaffold Next.js 15 project in dashboard-web/
- [x] Supabase client using public anon key (safe to expose in browser)
- [x] Alert feed: shows last 50 alerts with zone name, camera, timestamp, JPEG thumbnail
- [x] Store status: green/red dot based on heartbeat age (< 90 s = online)
- [x] Server component with `revalidate = 30` (refreshes every 30 s)
- [ ] Deploy to Vercel (add NEXT_PUBLIC_SUPABASE_URL + NEXT_PUBLIC_SUPABASE_ANON_KEY as env vars)

---

## Setup Checklist (new install)

1. Copy `.env.example` → `.env` and fill in `SUPABASE_URL`, `SUPABASE_KEY`, `STORE_ID`
2. Run `supabase/schema.sql` in Supabase SQL Editor
3. Create `alert-frames` Storage bucket in Supabase (set to Public)
4. Set `cloud.enabled: true` in `config.yaml`
5. `pip install -r requirements.txt`
6. `python -m shopguard`

For the Vercel dashboard:
1. Copy `dashboard-web/.env.local.example` → `dashboard-web/.env.local`
2. `cd dashboard-web && npm install && npm run dev`
3. Deploy: `vercel --cwd dashboard-web`
