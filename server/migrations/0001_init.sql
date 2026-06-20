-- EDITH Phase-1 schema (yoyo migration 0001).
--
-- Eight tables: users, provider_accounts, refresh_tokens, conversations,
-- messages, memories, action_log, usage_log. P1 stores identity-scope accounts
-- only; OAuth API tokens (*_enc) are reserved (NULL) until P2 and are app-layer
-- AES-GCM encrypted when populated. See docs/specs/phase-1-mvp.md (schema) and
-- the build plan A3.
--
-- depends:

-- gen_random_uuid() lives in pgcrypto.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ─── users ────────────────────────────────────────────────────────────────
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name    TEXT,
    primary_email   TEXT,
    preferred_voice TEXT,
    language_pref   TEXT,
    timezone        TEXT,
    onboarded       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A verified email is unique across users when present (drives account linking).
CREATE UNIQUE INDEX users_primary_email_key
    ON users (lower(primary_email))
    WHERE primary_email IS NOT NULL;

-- ─── provider_accounts ──────────────────────────────────────────────────────
-- One row per (user, OIDC provider). Identity in P1; *_enc API tokens in P2.
CREATE TABLE provider_accounts (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    provider          TEXT NOT NULL,            -- google | microsoft | apple
    provider_subject  TEXT NOT NULL,            -- the IdP 'sub' claim
    email             TEXT,
    scopes            TEXT,
    access_token_enc  BYTEA,                    -- P2; AES-GCM, NULL in P1
    refresh_token_enc BYTEA,                    -- P2; AES-GCM, NULL in P1
    token_expiry      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- The same IdP identity cannot map to two users.
    CONSTRAINT provider_accounts_provider_subject_key
        UNIQUE (provider, provider_subject),
    -- A user links at most one account per provider.
    CONSTRAINT provider_accounts_user_provider_key
        UNIQUE (user_id, provider)
);

-- ─── refresh_tokens ─────────────────────────────────────────────────────────
-- Hashed refresh tokens with a family_id for rotation + reuse-revocation: a
-- replayed (already-rotated) token revokes its whole family.
CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    family_id   UUID NOT NULL,
    token_hash  TEXT NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT refresh_tokens_token_hash_key UNIQUE (token_hash)
);

CREATE INDEX refresh_tokens_family_idx ON refresh_tokens (family_id);
CREATE INDEX refresh_tokens_user_created_idx ON refresh_tokens (user_id, created_at DESC);

-- ─── conversations ──────────────────────────────────────────────────────────
CREATE TABLE conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ,
    summary     TEXT
);

CREATE INDEX conversations_user_started_idx ON conversations (user_id, started_at DESC);

-- ─── messages ───────────────────────────────────────────────────────────────
CREATE TABLE messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role            TEXT NOT NULL,             -- user | edith | tool | system
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX messages_conversation_idx ON messages (conversation_id);
CREATE INDEX messages_user_created_idx ON messages (user_id, created_at DESC);

-- ─── memories ───────────────────────────────────────────────────────────────
-- Durable per-user facts. search_vector powers tsvector lexical recall (P1);
-- embeddings are deferred to P2+.
CREATE TABLE memories (
    id            BIGSERIAL PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    type          TEXT NOT NULL,              -- preference|fact|relationship|routine|location
    content       TEXT NOT NULL,
    source        TEXT NOT NULL,              -- tool | auto
    importance    SMALLINT NOT NULL DEFAULT 1,  -- 1..5
    search_vector TSVECTOR,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX memories_search_idx ON memories USING GIN (search_vector);
CREATE INDEX memories_user_type_idx ON memories (user_id, type);
CREATE INDEX memories_user_created_idx ON memories (user_id, created_at DESC);

-- Keep search_vector in sync with content (English config is fine for P1 lexical
-- recall; Manglish terms are indexed as-is by the 'simple'-like fallback).
CREATE FUNCTION memories_search_vector_update() RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', coalesce(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER memories_search_vector_trg
    BEFORE INSERT OR UPDATE OF content ON memories
    FOR EACH ROW EXECUTE FUNCTION memories_search_vector_update();

-- ─── action_log ─────────────────────────────────────────────────────────────
-- Every executed agent action, for trust/undo (distinct from debug logs).
CREATE TABLE action_log (
    id            BIGSERIAL PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    tool          TEXT NOT NULL,
    args_summary  TEXT,
    result        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX action_log_user_created_idx ON action_log (user_id, created_at DESC);

-- ─── usage_log ──────────────────────────────────────────────────────────────
-- Per-user metering (voice-seconds, tokens) — feeds billing in P6.
CREATE TABLE usage_log (
    id            BIGSERIAL PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    call_type     TEXT NOT NULL,
    voice_seconds NUMERIC(10, 3) NOT NULL DEFAULT 0,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX usage_log_user_created_idx ON usage_log (user_id, created_at DESC);
