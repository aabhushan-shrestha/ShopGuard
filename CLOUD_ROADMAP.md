# ShopGuard — Cloud & SaaS Roadmap

ShopGuard is transitioning from a local-only retail security tool into a hybrid SaaS product. The local agent continues to run at the store — handling camera feeds, person detection, and real-time alerts — while a new cloud layer enables remote monitoring, multi-store management, and a client-facing dashboard for store owners. This document tracks the full roadmap for that transformation.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                                 │
│                                                                     │
│   app.shopguard.com              admin.shopguard.com                │
│   (Store Owner Dashboard)        (Admin Dashboard — Aabhushan)      │
│   - Own store cameras/alerts     - All stores overview              │
│   - Clips, zones                 - Global alerts, system health     │
│   - Hosted on Vercel             - Store management                 │
│                                  - Hosted on Vercel                 │
└──────────────┬──────────────────────────────┬───────────────────────┘
               │                              │
               │         HTTPS / JWT          │
               ▼                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        CLOUD LAYER                                  │
│                                                                     │
│   FastAPI Backend (Railway)                                         │
│   - Agent endpoints: register, heartbeat, alert, clip upload        │
│   - Admin endpoints: stores, alerts, clips, health                  │
│   - Client endpoints: alerts, clips, zones (scoped to store)       │
│                                                                     │
│   Supabase (PostgreSQL)          Supabase Storage / Cloudflare R2   │
│   - stores, users, alerts        - Alert clip files                 │
│   - clips, heartbeats                                               │
└──────────────▲──────────────────────────────────────────────────────┘
               │
               │  HTTPS / API Key
               │  alerts, clips, heartbeats
               │
┌──────────────┴──────────────────────────────────────────────────────┐
│                        STORE LAYER                                  │
│                                                                     │
│   ShopGuard Local Agent (Python)                                    │
│   - Cameras: USB, iVCam, RTSP                                      │
│   - YOLOv8 detection + tracking                                     │
│   - Zone monitoring + behavior analysis                             │
│   - Alert handlers: console, Telegram, sound, webhook               │
│   - Clip recorder (ring buffer)                                     │
│   - CloudSync background thread → pushes to cloud API               │
│                                                                     │
│   Runs on store PC, works offline, syncs when connected             │
└─────────────────────────────────────────────────────────────────────┘
```

**Data flow:**

- **Agent → Cloud API:** alerts, clips, heartbeats (API key auth, background sync)
- **Cloud API → Admin dashboard:** all stores, all alerts, system health (JWT auth, admin role)
- **Cloud API → Client dashboard:** only that store's data (JWT auth, owner role)

---

## URL Structure

ShopGuard uses two separate dashboard URLs — one for store owners, one for the platform admin.

**app.shopguard.com** — Client Dashboard
- Store owners log in here
- See only their own store data
- Cameras, alerts, clips, zones
- Hosted on Vercel

**admin.shopguard.com** — Admin Dashboard
- Only Aabhushan (ShopGuard owner) logs in here
- Sees all stores, all customers
- Billing status, system health
- Store management and remote support
- Hosted on Vercel (separate deployment)

---

## Current Features (Local Agent — Completed)

- [x] YOLOv8 nano person detection
- [x] IoU-based person tracking with stable IDs
- [x] Polygon zone definition with browser-based editor
- [x] Per-camera zone storage (zones_camera_0.json etc.)
- [x] Behavior analysis: loitering, zone violations, pacing
- [x] Alert system with cooldown: console, file, sound, Telegram, webhook handlers
- [x] Ring-buffer clip recorder (pre + post event footage)
- [x] Local Flask dashboard with live feed, alerts, clips, zones tabs
- [x] Dark/light theme toggle
- [x] Camera switcher (USB + iVCam support)
- [x] Unsaved zone changes prompt on camera switch

---

## Phase A — RTSP Camera Connectivity

**Status:** :white_check_mark: Complete
**Goal:** ShopGuard works with any camera — phones, CCTVs, IP cameras — without requiring iVCam or USB connection

- [x] Accept RTSP URLs as camera source in config.yaml
- [x] Update camera.py to handle both integer index (USB) and string URL (RTSP) sources
- [x] Add RTSP camera management UI in dashboard camera selector
- [x] Add "Add RTSP Camera" form in dashboard (name + URL fields)
- [x] Persist RTSP camera list to config/cameras.json per store
- [ ] Test with Android phone running IP Webcam app
- [ ] Test with iPhone running Cameras for OBS
- [ ] Test with CCTV/DVR RTSP stream
- [x] Update PROGRESS.md

---

## Phase B — Cloud API Foundation

**Status:** :white_check_mark: Complete
**Goal:** A FastAPI server running on Railway that receives data from store agents and serves the master dashboards

**Technology:** FastAPI, Supabase (PostgreSQL + Storage), Railway, Python

**New folder:** cloud-api/ in same repo

- [x] Initialize FastAPI project in cloud-api/
- [x] Set up Supabase schema (tables below)
- [x] Implement store registration endpoint: POST /agent/register
- [x] Implement heartbeat endpoint: POST /agent/heartbeat
- [x] Implement alert forwarding endpoint: POST /agent/alert
- [x] Implement clip upload endpoint: POST /agent/clip
- [x] Implement admin endpoints: GET /admin/stores, GET /admin/alerts, GET /admin/clips
- [x] Implement client endpoints: GET /client/alerts, GET /client/clips, GET /client/zones
- [x] API key auth for agents, JWT auth for dashboard users
- [ ] Deploy to Railway (requires Railway account + live Supabase project)
- [x] Environment variables: Supabase URL, Supabase key, JWT secret (documented in .env.example)
- [x] Update PROGRESS.md

**Supabase Schema:**

```sql
-- Each store/customer
stores (id, name, address, api_key, plan, created_at, is_active)

-- Dashboard users (store owners + admin)
users (id, email, password_hash, store_id, role, created_at)
-- role: 'admin' = Aabhushan, 'owner' = store owner

-- Alerts forwarded from agents
alerts (id, store_id, camera_index, level, alert_type, 
        message, zone_name, person_id, timestamp, created_at)

-- Clip file references
clips (id, store_id, camera_index, alert_id, 
       filename, storage_url, duration_seconds, created_at)

-- Agent online/offline tracking
heartbeats (store_id, camera_index, last_seen, agent_version)
```

---

## Phase C — Agent Sync Layer

**Status:** :point_right: You are here
**Goal:** ShopGuard agent automatically syncs alerts, clips and heartbeats to the cloud in the background

**New file:** shopguard/sync.py

- [ ] Create CloudSync class in shopguard/sync.py
- [ ] Background thread — non-blocking, never slows detection loop
- [ ] On startup: register store with cloud API, store API key locally
- [ ] Every 30 seconds: send heartbeat (store_id, camera_index, agent_version)
- [ ] On alert fired: POST alert to cloud API with retry logic
- [ ] On clip saved: upload clip file to cloud storage, POST clip record
- [ ] Offline queue: if cloud unreachable, queue events and retry when back online
- [ ] Add sync config to config.yaml (cloud_api_url, store_id, enabled flag)
- [ ] Wire CloudSync into main.py
- [ ] Update PROGRESS.md

---

## Phase D — Master Dashboard (Two URLs)

**Status:** :black_large_square: Not started
**Goal:** Two separate web UIs hosted on Vercel — one for store owners, one for admin

### app.shopguard.com — Client Dashboard (Store Owner View)

- [ ] Login page (email + password)
- [ ] Store overview: camera status, today's alert count, last alert time
- [ ] Alert feed: filterable by camera, level, type — this store only
- [ ] Clip viewer: watch and download clips — this store only
- [ ] Zone manager: view and edit zones remotely (syncs to agent)
- [ ] Account settings
- [ ] Deploy to Vercel as app.shopguard.com

### admin.shopguard.com — Admin Dashboard (Your View)

- [ ] Login page (separate from client, admin credentials only)
- [ ] All stores overview: online/offline status, alert counts, last seen
- [ ] Global alert feed: all alerts across all stores
- [ ] Store detail: drill into any store's cameras, alerts, clips
- [ ] Store management: add/remove stores, regenerate API keys
- [ ] System health: agent versions, heartbeat status
- [ ] Deploy to Vercel as admin.shopguard.com

---

## Hosting & Services Summary

| Service | Purpose | Cost |
|---|---|---|
| Railway | FastAPI cloud API | Free tier to start |
| Supabase | PostgreSQL database | Free tier (500MB) |
| Supabase Storage | Clip files (early stage) | Free tier (1GB) |
| Vercel | app + admin dashboards | Free tier |
| Cloudflare R2 | Clip storage at scale | Free (10GB/month) |

---

## Licence & Legal Notes

- Current stack uses YOLOv8 (AGPL-3.0) — plan to export to ONNX before first paying customer
- ONNX Runtime licence is MIT — no commercial restrictions
- Store owners are responsible for CCTV legal compliance in their jurisdiction
- ShopGuard terms of service must clarify data ownership and retention policy
- Clip retention policy: auto-delete clips older than 30 days to control storage costs

---

## Session Notes

**2024 — Architecture decided**
- Hybrid model chosen: local agent + cloud sync
- Monorepo structure: agent + cloud-api + dashboards in one repo
- Two dashboard URLs: app.shopguard.com (clients) and admin.shopguard.com (admin)
- Supabase Storage for early stage, migrate to Cloudflare R2 at scale
- FastAPI chosen over Flask for cloud API
