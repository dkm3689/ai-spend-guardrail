-- Run this once against your Supabase / Neon Postgres database

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS projects (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT NOT NULL,
    owner_id         UUID,  -- Supabase auth user UUID; NULL for admin-created projects
    budget_daily     NUMERIC(10, 6),
    budget_monthly   NUMERIC(10, 6),
    enforcement_mode TEXT NOT NULL DEFAULT 'alert-only'
                         CHECK (enforcement_mode IN ('alert-only', 'visible-downgrade', 'hard-cap')),
    telegram_chat_id TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_keys (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    key_hash                TEXT NOT NULL UNIQUE,   -- SHA-256 of the proxy key
    provider_key_encrypted  TEXT NOT NULL,           -- Fernet-encrypted Anthropic key
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS requests (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id     UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    model          TEXT NOT NULL,
    input_tokens   INTEGER NOT NULL DEFAULT 0,
    output_tokens  INTEGER NOT NULL DEFAULT 0,
    cost           NUMERIC(12, 8) NOT NULL DEFAULT 0,
    was_downgraded BOOLEAN NOT NULL DEFAULT FALSE,
    was_blocked    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts_sent (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id    UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    threshold_pct INTEGER NOT NULL,
    sent_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- indexes for common dashboard queries
CREATE INDEX IF NOT EXISTS idx_requests_project_created ON requests (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_project_sent      ON alerts_sent (project_id, sent_at DESC);
