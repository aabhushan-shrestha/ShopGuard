-- ShopGuard — Supabase schema
-- Run this in Supabase SQL Editor to initialise the database.

-- ── Extensions ────────────────────────────────────────────────────────────────
create extension if not exists "pgcrypto";

-- ── Stores ────────────────────────────────────────────────────────────────────
create table if not exists stores (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    address     text not null default '',
    api_key     text not null unique,
    plan        text not null default 'free',
    is_active   boolean not null default true,
    created_at  timestamptz not null default now()
);

-- ── Users ─────────────────────────────────────────────────────────────────────
create table if not exists users (
    id            uuid primary key default gen_random_uuid(),
    email         text not null unique,
    password_hash text not null,
    store_id      uuid references stores(id) on delete set null,
    role          text not null check (role in ('admin', 'owner')),
    created_at    timestamptz not null default now()
);

-- ── Alerts ────────────────────────────────────────────────────────────────────
create table if not exists alerts (
    id            uuid primary key default gen_random_uuid(),
    store_id      uuid not null references stores(id) on delete cascade,
    camera_index  integer not null,
    level         text not null check (level in ('info', 'warning', 'critical')),
    alert_type    text not null,
    message       text not null,
    zone_name     text,
    person_id     integer,
    timestamp     timestamptz not null,
    created_at    timestamptz not null default now()
);

create index if not exists alerts_store_id_idx on alerts(store_id);
create index if not exists alerts_created_at_idx on alerts(created_at desc);

-- ── Clips ─────────────────────────────────────────────────────────────────────
create table if not exists clips (
    id               uuid primary key default gen_random_uuid(),
    store_id         uuid not null references stores(id) on delete cascade,
    camera_index     integer not null,
    alert_id         uuid references alerts(id) on delete set null,
    filename         text not null,
    storage_url      text not null,
    duration_seconds numeric(6,2),
    created_at       timestamptz not null default now()
);

create index if not exists clips_store_id_idx on clips(store_id);
create index if not exists clips_created_at_idx on clips(created_at desc);

-- ── Heartbeats ────────────────────────────────────────────────────────────────
create table if not exists heartbeats (
    store_id      uuid not null references stores(id) on delete cascade,
    camera_index  integer not null,
    last_seen     timestamptz not null default now(),
    agent_version text not null default 'unknown',
    primary key (store_id, camera_index)
);

-- ── Zones (synced from agent via Phase C) ─────────────────────────────────────
create table if not exists zones (
    store_id      uuid not null references stores(id) on delete cascade,
    camera_index  integer not null,
    data          jsonb not null default '[]'::jsonb,
    updated_at    timestamptz not null default now(),
    primary key (store_id, camera_index)
);

-- ── Row-level security (enable but keep permissive — enforced at API layer) ───
alter table stores     enable row level security;
alter table users      enable row level security;
alter table alerts     enable row level security;
alter table clips      enable row level security;
alter table heartbeats enable row level security;
alter table zones      enable row level security;

-- Service-role key bypasses RLS, so all API access goes through the server.
-- These policies grant nothing to anonymous/authenticated Supabase roles.
-- The FastAPI backend uses the service-role key and enforces its own auth.
