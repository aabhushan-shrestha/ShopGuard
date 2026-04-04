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
  ├─ camera.py  (RTSP)       ──►  heartbeats table     ◄──  Next.js app
  ├─ detector.py (YOLOv8)        alert-frames bucket        requires Gmail login
  ├─ tracker.py                                              reads only own data
  ├─ zones.py                RTSP credentials stay local,   via Supabase RLS
  ├─ behavior.py             only metadata + JPEG leaves
  ├─ alerts.py               the store PC
  ├─ recorder.py (local MP4)
  ├─ cloud.py ──────────────►  Supabase SDK (direct)
  │    └─ Google OAuth login    auth.uid() scopes all data
  ├─ api.py  (local Flask dashboard + zone editor)
  └─ main.py
```

**Auth:** Gmail login via Supabase Auth (Google OAuth + PKCE).  
On first launch with `cloud.enabled: true` a browser window opens for Google login.  
Session is saved to `~/.shopguard/session.json` and reused automatically.  
**RLS:** all rows scoped to `user_id = auth.uid()` — one store can never access another's data.  
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

**Goal:** Give each detected person a consistent ID so they can be followed across frames.

**Files:**
- `shopguard/tracker.py` — tracking logic
- `capture.py` — integrate tracker into the detection loop

**Tasks:**
- [x] Create `shopguard/tracker.py` with a `PersonTracker` class
- [x] Update `capture.py` to import and use `PersonTracker`
- [x] Verify visually: same person keeps the same ID as they move around
- [x] Handle edge cases: people entering/leaving frame, brief occlusions

---

## Phase 3: Zone Definition ✅ COMPLETE

**Goal:** Let the user define regions of interest so the system knows *where* things happen.

**Files:**
- `shopguard/zones.py` — zone creation and hit-testing
- `zone_editor.py` — interactive polygon zone editor

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

**Tasks:**
- [x] Store each person's position history
- [x] Detect loitering: person stays in the same zone for longer than a threshold
- [x] Detect zone violations: person enters a restricted zone
- [x] Detect unusual movement: pacing, repeated back-and-forth

---

## Phase 5: Alert System ✅ COMPLETE

**Goal:** When suspicious behavior is detected, notify staff immediately.

**Files:**
- `shopguard/alerts.py` — alert dispatcher with pluggable handlers
- `config.yaml` — alert settings

**Tasks:**
- [x] Define alert levels (info, warning, critical)
- [x] On-screen alert overlay
- [x] Sound alert
- [x] Log all alerts to `logs/alerts.log`
- [x] Telegram integration (optional)
- [x] Cooldown logic

---

## Phase 6: Recording & Evidence ✅ COMPLETE

**Goal:** Automatically save video clips around suspicious events for later review.

**Files:**
- `shopguard/recorder.py` — clip saving logic

**Tasks:**
- [x] Buffer the last N seconds of frames in memory (ring buffer)
- [x] When an alert fires, save a clip: 10s before + 10s after
- [x] Filename includes timestamp and event type
- [x] Save a snapshot image with bounding boxes drawn

---

## Phase 7: Local Dashboard ✅ COMPLETE

**Goal:** A local web interface on the store PC to review alerts and manage zones.

**Files:**
- `shopguard/api.py` — Flask app, DashboardState, all routes
- `dashboard/templates/index.html` — single-page dashboard UI

**Tasks:**
- [x] Live view of the camera feed in the browser
- [x] Alert feed showing recent events
- [x] Clip playback from saved recordings
- [x] Zone editor in the browser (click-to-draw polygons)
- [x] Basic auth so only staff can access it

---

## Phase A: RTSP Camera Connectivity ✅ COMPLETE

**Goal:** ShopGuard works with any network camera — phones, CCTVs, IP cameras.

**Files:**
- `shopguard/camera.py` — handles int (USB) and string (RTSP) sources
- `shopguard/api.py` — RTSP camera CRUD endpoints
- `config.yaml` — source field accepts int or RTSP URL string

**Tasks:**
- [x] Accept RTSP URLs as camera source in config.yaml
- [x] Update camera.py to handle both USB index and RTSP URL
- [x] Add RTSP camera management UI in local dashboard
- [x] Persist RTSP camera list to config/cameras.json

---

## Phase B: Cloud API Foundation ~~SUPERSEDED~~

> **Superseded by Phase C.** The FastAPI/Railway server has been removed.
> The local agent now talks directly to Supabase — no middleman.
> The `cloud-api/` directory has been deleted from the repo.

---

## Phase C: Direct Supabase Integration ✅ COMPLETE

**Goal:** Local agent pushes alert metadata and JPEG frames directly to Supabase.

**Files:**
- `shopguard/cloud.py` — SupabaseCloud: heartbeat, alert upload, frame upload
- `shopguard/main.py` — wires in SupabaseCloud
- `supabase/schema.sql` — alerts + heartbeats tables + RLS
- `config.yaml` — `cloud:` section
- `requirements.txt` — added supabase>=2.0.0, python-dotenv>=1.0.0

**Tasks:**
- [x] Create `shopguard/cloud.py` with `SupabaseCloud` class
- [x] Heartbeat: background thread upserts `heartbeats` row every 60 s
- [x] Alert: upload JPEG frame to `alert-frames` bucket
- [x] Alert: insert row to `alerts` table
- [x] All Supabase I/O in daemon threads
- [x] Delete `cloud-api/` (FastAPI/Railway server)

---

## Phase D: Vercel Dashboard ✅ COMPLETE

**Goal:** A Next.js frontend on Vercel that reads alerts and heartbeats from Supabase.

**Files:**
- `dashboard-web/app/page.tsx` — server component: alert feed + store status
- `dashboard-web/lib/supabase.ts` — Supabase client + types + isOnline helper
- `dashboard-web/package.json` — Next.js 15, @supabase/supabase-js

**Tasks:**
- [x] Scaffold Next.js 15 project in dashboard-web/
- [x] Alert feed: last 50 alerts with zone, camera, timestamp, JPEG thumbnail
- [x] Store status: green/red dot based on heartbeat age (< 90 s = online)
- [x] Server component with `revalidate = 30`

---

## Phase E: Gmail Auth (Supabase Auth) ✅ COMPLETE

**Goal:** Replace manual store_id with real user accounts. Each store owner logs in with
Gmail — their Google identity scopes all data automatically via Supabase RLS.
No API keys, no store IDs, no passwords stored anywhere.

**Files:**
- `shopguard/cloud.py` — PKCE Google OAuth login on first run, session persistence
- `supabase/schema.sql` — `user_id uuid references auth.users` replaces `store_id text`; RLS uses `auth.uid()`
- `dashboard-web/lib/supabase.ts` — server + browser Supabase clients via `@supabase/ssr`
- `dashboard-web/middleware.ts` — session refresh middleware
- `dashboard-web/app/login/page.tsx` — "Sign in with Google" page
- `dashboard-web/app/auth/callback/route.ts` — OAuth callback handler
- `dashboard-web/app/components/LogoutButton.tsx` — client-side sign-out button
- `dashboard-web/app/page.tsx` — auth check → redirect to /login if unauthenticated
- `dashboard-web/package.json` — added @supabase/ssr
- `.env` — SUPABASE_ANON_KEY (was SUPABASE_KEY), removed STORE_ID
- `config.yaml` — removed store_id field

**Tasks:**
- [x] Local agent: PKCE Google OAuth login on first launch
- [x] Local agent: save session to `~/.shopguard/session.json`, restore on restart
- [x] Local agent: use `user_id` from auth session instead of manual `store_id`
- [x] Schema: `alerts.user_id` and `heartbeats.user_id` reference `auth.users`
- [x] RLS: `authenticated` role with `auth.uid() = user_id` on all tables
- [x] Dashboard: Gmail login page with Google OAuth button
- [x] Dashboard: `/auth/callback` route exchanges code for session
- [x] Dashboard: `middleware.ts` refreshes session on every request
- [x] Dashboard: main page redirects to `/login` if not authenticated
- [x] Dashboard: "Sign out" button
- [x] RTSP credentials still never leave the store PC
- [ ] Enable Google provider in Supabase: Authentication > Providers > Google
- [ ] Add Google OAuth Client ID + Secret in Supabase
- [ ] Add redirect URL in Supabase: `https://your-project.supabase.co/auth/v1/callback`
- [ ] Deploy to Vercel (add NEXT_PUBLIC_SUPABASE_URL + NEXT_PUBLIC_SUPABASE_ANON_KEY)

---

## Setup Checklist (new install)

### Supabase (one-time)
1. Run `supabase/schema.sql` in Supabase SQL Editor
2. Create `alert-frames` Storage bucket (set to Public)
3. Enable Google OAuth: Authentication > Providers > Google
4. Add your Google OAuth Client ID and Secret
5. Add redirect URL: `https://<project>.supabase.co/auth/v1/callback`

### Local agent
1. Copy `.env.example` → `.env` — fill in `SUPABASE_URL` and `SUPABASE_ANON_KEY` only
2. Set `cloud.enabled: true` in `config.yaml`
3. `pip install -r requirements.txt`
4. `python -m shopguard` — browser opens for Google login on first run

### Vercel dashboard
1. Copy `dashboard-web/.env.local.example` → `dashboard-web/.env.local`
2. Fill in `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`
3. `cd dashboard-web && npm install && npm run dev`
4. Deploy: `vercel --cwd dashboard-web`
5. Add the same two env vars in Vercel project settings
