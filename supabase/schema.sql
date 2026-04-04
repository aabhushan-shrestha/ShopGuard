-- ShopGuard — Supabase schema
-- Run this in the Supabase SQL Editor to initialise the database.
--
-- Authentication: Gmail login via Supabase Auth (Google OAuth provider).
-- RLS ensures each user sees and writes only their own data.
-- The local store agent authenticates once via browser (PKCE) and reuses
-- the saved session on subsequent launches.

-- ── Alerts ────────────────────────────────────────────────────────────────────
-- One row per fired alert.  The agent inserts; the dashboard reads.
create table if not exists alerts (
    id            uuid        primary key default gen_random_uuid(),
    user_id       uuid        not null references auth.users(id) on delete cascade,
    camera_index  text        not null default '0',
    zone_name     text        not null default '',
    timestamp     timestamptz not null,
    image_url     text,                           -- public URL in Storage bucket
    created_at    timestamptz not null default now()
);

create index if not exists alerts_user_id_idx    on alerts (user_id);
create index if not exists alerts_created_at_idx on alerts (created_at desc);

-- ── Heartbeats ────────────────────────────────────────────────────────────────
-- One row per user (store), upserted every 60 s by the local agent.
-- Dashboard uses last_seen to show online/offline status (threshold: 90 s).
create table if not exists heartbeats (
    user_id    uuid        primary key references auth.users(id) on delete cascade,
    last_seen  timestamptz not null default now(),
    created_at timestamptz not null default now()
);

-- ── Row-Level Security ────────────────────────────────────────────────────────
alter table alerts     enable row level security;
alter table heartbeats enable row level security;

-- Authenticated users can insert their own alerts.
create policy "users can insert own alerts"
    on alerts for insert to authenticated
    with check (auth.uid() = user_id);

-- Authenticated users can read their own alerts only.
create policy "users can read own alerts"
    on alerts for select to authenticated
    using (auth.uid() = user_id);

-- Authenticated users can manage their own heartbeat row.
create policy "users can manage own heartbeat"
    on heartbeats for all to authenticated
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- ── Storage bucket ────────────────────────────────────────────────────────────
-- Create manually in Supabase dashboard: Storage > New bucket > "alert-frames"
-- Set bucket visibility to Public so image_url links work without extra auth.
-- Alert frames are scoped to user_id/ prefix in the bucket path.
--
-- Optional: add Storage RLS policy to restrict access by user:
--   create policy "users can manage own frames"
--     on storage.objects for all to authenticated
--     using (bucket_id = 'alert-frames' and (storage.foldername(name))[1] = auth.uid()::text)
--     with check (bucket_id = 'alert-frames' and (storage.foldername(name))[1] = auth.uid()::text);
--
-- ── Google OAuth provider ─────────────────────────────────────────────────────
-- Enable in Supabase dashboard: Authentication > Providers > Google
-- Add your Google OAuth Client ID and Secret.
-- Add redirect URL: https://your-project.supabase.co/auth/v1/callback
