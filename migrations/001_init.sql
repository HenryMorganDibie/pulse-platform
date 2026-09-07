-- Pulse Platform — initial schema
-- Run against Supabase (or any Postgres with the pgvector extension available).

create extension if not exists pgvector;
create extension if not exists pgcrypto; -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- Tenants — one row per customer business using the platform. Provisioned via
-- scripts/create_tenant.py (admin-only), never via a public endpoint.
-- ---------------------------------------------------------------------------
create table tenants (
    id            uuid primary key default gen_random_uuid(),
    name          text not null,
    plan          text not null default 'free',
    created_at    timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- API keys — split from tenants so a compromised key can be revoked without
-- touching the tenant row, and so a tenant can hold more than one key later
-- without a schema change. key_prefix (e.g. "pk_live_ab12") is shown back to
-- the tenant for identifying a key in a list without ever re-displaying it.
-- ---------------------------------------------------------------------------
create table api_keys (
    id           uuid primary key default gen_random_uuid(),
    tenant_id    uuid not null references tenants(id) on delete cascade,
    key_hash     text not null unique,
    key_prefix   text not null,
    created_at   timestamptz not null default now(),
    revoked_at   timestamptz
);

create index api_keys_tenant_idx on api_keys(tenant_id);

-- ---------------------------------------------------------------------------
-- Subjects — a tenant's own end-user, keyed by the tenant's external id for them.
-- ---------------------------------------------------------------------------
create table subjects (
    id           uuid primary key default gen_random_uuid(),
    tenant_id    uuid not null references tenants(id) on delete cascade,
    external_id  text not null,
    created_at   timestamptz not null default now(),
    unique (tenant_id, external_id)
);

-- ---------------------------------------------------------------------------
-- Review records — append-only interaction history feeding persona construction.
-- ---------------------------------------------------------------------------
create table review_records (
    id          uuid primary key default gen_random_uuid(),
    subject_id  uuid not null references subjects(id) on delete cascade,
    item_id     text not null,
    category    text not null,
    rating      numeric(2,1) not null check (rating >= 1.0 and rating <= 5.0),
    text        text not null default '',
    timestamp   timestamptz,
    created_at  timestamptz not null default now()
);

create index review_records_subject_idx on review_records(subject_id);

-- ---------------------------------------------------------------------------
-- User states — cached persona, one row per subject. Invalidated (stale=true)
-- whenever a new review_record lands; recomputed lazily on next read.
-- ---------------------------------------------------------------------------
create table user_states (
    subject_id        uuid primary key references subjects(id) on delete cascade,
    behavioural       jsonb not null,
    textual           jsonb not null,
    contextual        jsonb not null,
    pipeline_errors   jsonb not null default '[]'::jsonb,
    computed_at       timestamptz not null default now(),
    stale             boolean not null default false
);

-- ---------------------------------------------------------------------------
-- Catalog items — tenant-scoped inventory for the Recommend product.
-- embedding dimension matches sentence-transformers/all-MiniLM-L6-v2 (384).
-- embedding_model is stamped on every write so a future model change is a
-- detectable "embedding_model != current config" condition, not a silent
-- mismatch between old and new vectors in the same ivfflat index.
-- ---------------------------------------------------------------------------
create table catalog_items (
    id               uuid primary key default gen_random_uuid(),
    tenant_id        uuid not null references tenants(id) on delete cascade,
    item_id          text not null,
    name             text not null,
    category         text not null,
    attributes       jsonb not null default '{}'::jsonb,
    embedding        vector(384),
    embedding_model  text,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    unique (tenant_id, item_id)
);

create index catalog_items_tenant_idx on catalog_items(tenant_id);
create index catalog_items_embedding_idx on catalog_items
    using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- ---------------------------------------------------------------------------
-- Request log — thin usage record per product call. Not billing itself, but
-- means billing/metering later doesn't require a schema migration to add.
-- ---------------------------------------------------------------------------
create table request_log (
    id          uuid primary key default gen_random_uuid(),
    tenant_id   uuid not null references tenants(id) on delete cascade,
    subject_id  uuid references subjects(id) on delete set null,
    product     text not null check (product in ('simulate', 'recommend')),
    created_at  timestamptz not null default now()
);

create index request_log_tenant_idx on request_log(tenant_id, created_at);
