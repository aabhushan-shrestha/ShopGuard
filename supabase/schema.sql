-- ShopGuard — Supabase schema
-- Run this in the Supabase SQL Editor to initialise the database.
--
-- Architecture: the local store agent (shopguard/) writes directly to Supabase
-- using the anon key.  The Vercel dashboard reads directly from Supabase.
-- No backend server sits in between.

-- ── Alerts ────────────────────────────────────────────────────────────────────
-- One row per fired alert.  The agent inserts; the dashboard reads.
create table if not exists alerts (
    id            uuid        primary key default gen_random_uuid(),
    store_id      text        not null,
    camera_index  text        not null default '0',
    zone_name     text        not null default '',
    timestamp     timestamptz not null,
    image_url     text,                           -- public URL in Storage bucket
    created_at    timestamptz not null default now()
);

create index if not exists alerts_store_id_idx   on alerts (store_id);
create index if not exists alerts_created_at_idx on alerts (created_at desc);

-- ── Heartbeats ────────────────────────────────────────────────────────────────
-- One row per store, upserted every 60 s by the local agent.
-- Dashboard uses last_seen to show online/offline status (threshold: 90 s).
create table if not exists heartbeats (
    store_id   text        primary key,
    last_seen  timestamptz not null default now(),
    created_at timestamptz not null default now()
);

-- ── Row-Level Security ────────────────────────────────────────────────────────
alter table alerts     enable row level security;
alter table heartbeats enable row level security;

-- Agents (anon key) can insert alerts.
create policy "agents can insert alerts"
    on alerts for insert to anon
    with check (true);

-- Dashboard (anon key) can read all alerts.
create policy "dashboard can read alerts"
    on alerts for select to anon
    using (true);

-- Agents can upsert their own heartbeat row.
create policy "agents can upsert heartbeats"
    on heartbeats for all to anon
    using (true)
    with check (true);

-- ── Storage bucket ────────────────────────────────────────────────────────────
-- Create manually in Supabase dashboard: Storage > New bucket > "alert-frames"
-- Set bucket visibility to Public so image_url links work without auth.
