# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

**Through P5 (server), text+voice, mobile.** Built and tested (125 server tests + ruff + mypy; Flutter analyze + build apk): agent runtime · real **Google OIDC login** + JWT sessions · Postgres persistence · ILMU **voice** (ASR/TTS + VAD + barge-in, live-verified) · **P2 wedge** Gmail + Calendar + Contacts over OAuth (encrypted tokens) · **P3 proactivity** (scheduler + reminders + push seam + device registration) · **P4** WhatsApp Business **Cloud API** send (CONFIRM) · **P5** Home Assistant smart-home (read AUTO / control CONFIRM). Flutter client: web + Android/iOS, SSO, on-device voice, Android home-screen widget.

**Roadmap status & boundaries.** Device-only pieces (P4 Android WhatsApp NotificationListener assist, on-device wake word) are native/device-verified, delegated to the app and clearly marked "needs a device." **P6 monetization stays OUT of this public repo** — per the open-core split in `docs/engineering.md` (`.gitignore` reserves `server/app/billing/`), billing/subscriptions are the private commercial layer that *plugs into* the core; the public core ships the **metering seam** only (`usage_log` records voice-seconds + tokens; free tier is time-based). Going live still needs *your* credentials (ILMU key; Google OAuth client; optional FCM/WhatsApp/Home-Assistant tokens) — see `docs/SETUP.md`.

The source-of-truth documents remain authoritative — read them before extending:

- `docs/specs/product-design.md` — full vision, locked architecture, trust model, integration feasibility, 6-phase roadmap
- `docs/specs/phase-1-mvp.md` — detailed Phase 1 build plan: gating spikes, build order, streaming/agent protocol, auth flow, DB schema

Follow the directory layout and module responsibilities in those specs when scaffolding.

## What EDITH is

EDITH (Everyday Digital Intelligent Task Helper) is a **Malaysia-first, voice-first AI agent** for non-technical users: sign in, talk in **Bahasa Malaysia / English / Manglish**, and EDITH **takes actions** through connected apps (calendar, email, contacts, WhatsApp) and proactively notifies you. Mobile-first (Android/iOS) with a web trial surface. The local-language voice quality is the core differentiator vs. Siri/ChatGPT/Alexa. Ported in spirit from a prior single-user project, **JARVIS** (the specs map JARVIS components to EDITH equivalents).

## Architecture (locked)

```
Flutter (Web/Android/iOS) ⇄ FastAPI on Azure Container Apps (MY region) ⇄ ILMU ASR/TTS API
   (bidirectional audio)         │ server-mediated TURN-BASED pipeline (ILMU is file/batch, not streaming)
                                 ├─ VAD endpoint → batch ASR; per-sentence TTS; barge-in on playback
                                 ├─ Agent core: tool registry + exec + confirmation
                                 ├─ LLM layer: nemo-super (tools/reasoning) · ilmu-v3.1 (Manglish gen)
                                 ├─ per-user memory injection (tsvector + bge-m3 embeddings)
                                 ├─ OIDC auth (Google/Microsoft/Apple) + own JWTs
                                 └─ Azure Postgres (asyncpg)
```

Voice path: `mic → VAD endpoint → ILMU ASR (file) → [nemo-super + agent] → ILMU TTS (per sentence) → speaker`; user speech during playback triggers **barge-in** (cancel TTS+LLM, new turn). ~3s to first audio. See [ADR 0002](docs/decisions/0002-voice-and-agent-llm-from-ilmu-spike.md).

- `server/` — Python 3.12 FastAPI. One `/ws` WebSocket per user carries a continuous bidirectional audio channel, but **turns are batch** (VAD endpoints an utterance → file ASR; TTS synthesized per sentence). Subsystems: `voice/` (ILMU ASR/TTS, VAD, pipeline orchestration), `agent/` (LLM abstraction + tool registry + execution + confirmation), `auth/` (OIDC RP + JWT sessions), `integrations/` (OAuth, P2+), `proactivity/` (scheduler + push, P3), `memory.py`, `db.py`.
- `app/` — Flutter (Dart), Riverpod. `voice/`+`audio/` do bidirectional streaming with barge-in; `orb/` is a GLSL fragment-shader visual driven by the live stream; `linking/` is the integration hub; `android/` holds native code (WhatsApp NotificationListener + reply, widget).

### Decisions that shape the whole codebase

- **Voice is a TURN-BASED pipeline (ILMU is file/batch — confirmed no streaming; [ADR 0002](docs/decisions/0002-voice-and-agent-llm-from-ilmu-spike.md)).** **ILMU ASR + TTS** chosen for Manglish quality (validated excellent). Responsiveness is engineered via *pseudo-streaming*: VAD-tight utterances → batch ASR; token-stream the LLM; synthesize **TTS per sentence** played back-to-back; **barge-in on playback**. ~3s to first audio. The `StreamingASR`/`StreamingTTS` interfaces absorb the batch reality — the agent loop/Transport don't change. No OpenAI Realtime harness.
- **Agent LLM is single-vendor (YTL/ILMU API): `nemo-super` for tools/reasoning** (validated reliable at tool-calling + relative-date math), `ilmu-v3.1` available for Manglish-heavy generation. **Do NOT use `ilmu-v3.1` for tool-calling** (proven unreliable). Frontier (Claude/GPT) is only an optional escape hatch behind the LLM abstraction, not a default dependency.
- **Server-mediated, always.** Client audio flows *through* our server. Tools, memory, confirmation, keys, metering live server-side. Never connect the client directly to a model provider.
- **Agent core from day one.** Every capability is a **tool registered with the agent**, classed `auto` (run immediately) or `confirm` (round-trip a `confirm_request`/`confirm` first). Later integrations are just more tools — don't special-case them.
- **Trust model is cross-cutting.** Auto-execute reversible/local/read actions; **verbally confirm** external/irreversible ones (send email, send WhatsApp reply, delete, modify others' meetings, unlock). Enforced by the tool's class; every action logged to `action_log`.
- **Multi-tenant from day one.** No global state — everything keyed by `user_id`/connection. Porting JARVIS code means removing single-user globals and threading `user_id` everywhere.
- **Self-hosted SSO auth (no Supabase, no passwords).** OIDC relying party to Google/Microsoft/Apple; own JWT sessions (access + refresh, hashed + revocable). **Incremental scopes**: identity at login; API scopes just-in-time at feature activation, reusing the provider credential. **Apple is identity-only**.
- **Direct Postgres on Azure** via **asyncpg** (no ORM); schema as **plain-SQL yoyo migrations**; memory search via `tsvector` (lexical) and/or ILMU `bge-m3` embeddings + `bge-reranker` (semantic). Host in the **Malaysia/Southeast-Asia region** (latency to users + ILMU API).
- **WhatsApp has two separate tracks — never scrape WhatsApp Web.** (1) *Personal assist* = **Android on-device** via NotificationListenerService (read) + notification direct-reply/RemoteInput (send); official OS APIs, no server session, zero per-message cost, **iOS cannot do this**. (2) *EDITH's own number* = compliant **WhatsApp Business Cloud API**, a separate optional reach/SMB channel. Server-side WhatsApp Web scraping is explicitly rejected (ban/ToS/security risk).
- **Cost is first-class.** Free tier is **time-based** (voice-minutes); per-user metering ships in Phase 1 (`usage_log.voice_seconds`).
- **ILMU spike: DONE (2026-06-20, [ADR 0002](docs/decisions/0002-voice-and-agent-llm-from-ilmu-spike.md)).** Findings: no streaming (→ turn-based); Manglish ASR excellent; `ilmu-v3.1` unreliable at tools; **`nemo-super` validated** for tool-calling; `bge-m3`/`bge-reranker` available. All endpoints OpenAI-compatible (`https://api.ilmu.ai/v1`).

### Roadmap shape

P1 Foundation + agent core (+ gating spikes) → P2 wedge (calendar/email/contacts) → P3 proactivity (push, tap-to-engage) → P4 ambient invocation + WhatsApp Android assist → P5 reach (smart home, desktop, local agent) → P6 monetization. Proactivity depends on the wedge being connected; keep that ordering.

## Commands

**Status: M1 implemented** (text-mode end-to-end). The server is a runnable FastAPI app with real Postgres persistence, JWT session auth, and the ILMU `nemo-super` LLM (falls back to a deterministic `StubLLM` when `ILMU_API_KEY` is unset). The Flutter text client is scaffolded. Voice (ASR/TTS/VAD pipeline) is M2.

Local dev (from repo root unless noted):

```bash
docker compose up -d postgres          # Postgres on host port 5434 (5432/5433 taken)
# server (from server/, with a .venv created via: uv sync --all-extras --dev)
uvicorn app.main:app --reload          # applies migrations on startup, opens the pool
.venv/bin/python -m pytest             # 54 tests; DB tests auto-skip if Postgres is down
.venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests
.venv/bin/mypy app
docker compose build server            # build the deploy image (python 3.12)
# app (from app/)
flutter pub get && flutter analyze && flutter test
```

Auth for local use: `POST /auth/dev-login {"email","display_name"}` → tokens (non-production only); then open `/ws` with `{"type":"auth","token":"<access>"}`. To let EDITH **read email**, set `GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD` (a Google App Password) in `server/.env` — the `gmail` connector's `read_recent_emails`/`search_emails` tools then go live.
