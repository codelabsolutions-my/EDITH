# EDITH — Setup guide

How to run EDITH end to end: the FastAPI server, Postgres, the Flutter app
(web/Android/iOS), voice, login, and the Gmail / Calendar / Contacts integrations.

Status of what this guide covers: **M2** — text **and** voice agent, real Google
login, and the P2 wedge (email + calendar + contacts) over OAuth. Some features
need credentials only you can create (an ILMU key, a Google OAuth client); each is
called out as **required** or **optional**, and EDITH degrades gracefully without
the optional ones.

---

## 0. Prerequisites

| Tool | Version | For |
|------|---------|-----|
| Docker + Docker Compose | any recent | Postgres (and optionally the server image) |
| Python | 3.12+ (3.14 works locally) | the server |
| [uv](https://docs.astral.sh/uv/) | latest | server deps/venv (or use `pip`) |
| Flutter | 3.44+ | the app (`flutter`, `dart` on PATH) |

---

## 1. Configuration (`.env`)

```bash
cp .env.example .env            # repo root reference
cp .env.example server/.env     # the server reads server/.env
```

Edit `server/.env`. The **only values required** to boot are already filled with
working dev defaults:

- `DATABASE_URL=postgresql://edith:edith@localhost:5434/edith` (matches the compose DB)
- `JWT_SECRET=<dev value>` and `TOKEN_ENCRYPTION_KEY=<base64 32 bytes>` (rotate for prod)

Everything else is **optional** and unlocks a feature when set (below).

> `.env` files are gitignored — never commit real secrets.

---

## 2. Database

```bash
docker compose up -d postgres   # Postgres 16 on host port 5434
```

Migrations apply automatically on server startup (yoyo). To check:

```bash
docker compose ps               # postgres should be "healthy"
```

The server also runs **without** a reachable DB (in-memory fallback) — handy for a
quick text demo — but persistence, login, and integrations need Postgres.

---

## 3. Server

```bash
cd server
uv sync --all-extras --dev          # or: python -m venv .venv && pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload   # http://localhost:8000
```

Health check: `curl localhost:8000/healthz` → `{"status":"ok"}`.

Run the test suite (DB-backed tests auto-skip if Postgres is down):

```bash
.venv/bin/python -m pytest          # 107 tests
.venv/bin/ruff check app tests && .venv/bin/mypy app
```

### Voice + the real LLM (optional, recommended) — ILMU key

Set in `server/.env`:

```
ILMU_API_BASE=https://api.ilmu.ai/v1
ILMU_API_KEY=<your key>
ILMU_TOOL_MODEL=nemo-super
ILMU_ASR_MODEL=ilmu-asr-v4.2
ILMU_TTS_MODEL=ilmu-tts-v2
ILMU_TTS_VOICE=voice_2
```

Without a key, EDITH still runs in text mode with a deterministic stub LLM (good for
tests/dev); with it, the agent uses `nemo-super` and voice (ASR/TTS) turns on.

---

## 4. Logging in

Two paths:

- **Dev login (no setup, non-production only):**
  `POST /auth/dev-login {"email":"you@example.com","display_name":"You"}` → tokens.
- **Real Google sign-in (optional):** the app's "Sign in with Google" button gets a
  Google **ID token** and calls `POST /auth/google {"id_token":"…"}`. Requires a
  Google OAuth client (next section).

Open the WebSocket with the returned access token:
`{"type":"auth","token":"<access>"}` (add `"mode":"voice"` for voice).

---

## 5. Google OAuth (optional) — login + Gmail/Calendar/Contacts

One Google Cloud OAuth client powers Google **login** and the **read-only** Gmail,
Calendar, and Contacts integrations (incremental scopes — one consent per service).

1. In [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services**:
   - Enable: **Gmail API**, **Google Calendar API**, **People API**.
   - **OAuth consent screen**: add scopes `gmail.readonly`, `calendar.readonly`,
     `contacts.readonly`; add yourself as a test user.
   - **Credentials → OAuth client ID**:
     - **Web application** — Authorized redirect URI:
       `http://localhost:8000/integrations/google/callback`
       (use your real origin in prod; it must equal `PUBLIC_BASE_URL` + that path).
     - For mobile, also create **Android** and **iOS** OAuth client IDs.
2. In `server/.env`:
   ```
   GOOGLE_CLIENT_ID=<web client id>
   GOOGLE_CLIENT_SECRET=<web client secret>
   GOOGLE_ALLOWED_AUDIENCES=<android client id>,<ios client id>
   PUBLIC_BASE_URL=http://localhost:8000
   ```
   (`GOOGLE_ALLOWED_AUDIENCES` lets the server accept id_tokens minted for the mobile
   clients during login.)

### Connecting a service (after logging in)

Open these in a browser (they redirect to Google consent, then store an **encrypted**
token and return you to a success page):

```
http://localhost:8000/integrations/google/gmail/connect?token=<access JWT>
http://localhost:8000/integrations/google/calendar/connect?token=<access JWT>
http://localhost:8000/integrations/google/contacts/connect?token=<access JWT>
```

Then ask EDITH "read my latest emails", "what's on my calendar", "what's Ali's number".

### Gmail without OAuth (fast fallback)

To read Gmail with no Cloud project, use a Google **App Password** (Account →
Security → 2-Step Verification → App passwords) in `server/.env`:

```
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=<16-char app password>
```

The gmail connector prefers OAuth when present and falls back to IMAP otherwise.

---

## 6. The app (Flutter)

```bash
cd app
flutter pub get
flutter run -d chrome        # web (easiest to try)
# or:  flutter run            # a connected Android/iOS device/emulator
```

Point the app at your server with `--dart-define` if not on localhost:8000, e.g.
`flutter run -d chrome --dart-define=EDITH_BASE_URL=http://localhost:8000`.

- **Text**: type in the chat. **Voice**: toggle voice mode and talk (mic permission).
- **Login**: "Sign in with Google" (needs the mobile/web Google client IDs configured
  in the app + server), or the dev-login fallback.
- **Android widget**: `flutter build apk` and install; add the EDITH widget to your
  home screen — tap launches a voice session.

Checks: `flutter analyze`, `flutter test`, `flutter build apk --debug`.

---

## 7. Quick smoke test (text, no external accounts)

```bash
docker compose up -d postgres
cd server && .venv/bin/uvicorn app.main:app &
# dev-login → token → WebSocket → "what time is it" (uses the stub LLM without an ILMU key)
```

A live voice round-trip and the Gmail/Calendar/Contacts reads need the ILMU key and a
Google grant respectively.

---

## 8. What needs you vs. what's automatic

| Works out of the box | Needs your credential |
|---|---|
| Postgres (compose), migrations, server, text agent (stub LLM), dev-login, tests | — |
| — | Voice + smart replies → **ILMU key** |
| — | Google login + Gmail/Calendar/Contacts → **Google OAuth client** (or Gmail App Password for email only) |
| — | Live mic/speaker + the home-screen widget → a **real device/emulator** |

---

## Production notes

- Rotate `JWT_SECRET` and `TOKEN_ENCRYPTION_KEY` (32 bytes, base64); set `ENV=production`.
- Build the server image: `docker compose build server` (Python 3.12). Deploy target is
  Azure Container Apps in a Malaysia/SEA region (latency to users + ILMU).
- Set `PUBLIC_BASE_URL` to your real origin and register the matching OAuth redirect URI.
