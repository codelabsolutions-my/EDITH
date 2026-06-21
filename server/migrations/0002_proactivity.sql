-- EDITH P3 proactivity schema (yoyo migration 0002).
--
-- device_tokens: push targets per user/platform (FCM / APNs / web push).
-- reminders: one-shot scheduled nudges the proactive scheduler delivers.
--
-- depends: 0001_init

-- ─── device_tokens ──────────────────────────────────────────────────────────
CREATE TABLE device_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    platform    TEXT NOT NULL,             -- fcm | apns | web
    token       TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- The same device token registers once (re-registration refreshes it).
    CONSTRAINT device_tokens_token_key UNIQUE (token)
);

CREATE INDEX device_tokens_user_idx ON device_tokens (user_id);

-- ─── reminders ──────────────────────────────────────────────────────────────
CREATE TABLE reminders (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    text        TEXT NOT NULL,
    remind_at   TIMESTAMPTZ NOT NULL,
    delivered   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The scheduler polls due, undelivered reminders ordered by time.
CREATE INDEX reminders_due_idx ON reminders (remind_at) WHERE NOT delivered;
CREATE INDEX reminders_user_idx ON reminders (user_id, remind_at DESC);
