# EDITH — Phase 1 MVP Plan

> Detailed build plan for the MVP. Product context: `docs/specs/product-design.md`.

## Scope (MVP)

1. SSO sign-in (Google / Microsoft / Apple) on web or mobile
2. **Fast BM/Manglish voice turns** via the ILMU turn-based pipeline (speech in, speech out, ~3s, **barge-in** on playback), mirrored as on-screen text
3. **Agent core**: EDITH calls tools mid-conversation; risky tools wait for confirmation
4. Conversational memory persists across sessions
5. Orb renders smoothly from the live audio stream
6. Per-user voice-minute metering; 10+ concurrent users, full isolation

> **ILMU spike: DONE (2026-06-20) — see [ADR 0002](../decisions/0002-voice-and-agent-llm-from-ilmu-spike.md).** Outcomes baked into this plan:
> - ASR/TTS are **file/batch (no streaming)** → voice is **turn-based + pseudo-streaming** (per-sentence TTS). Manglish ASR validated excellent. ~2s ASR, ~1.7s TTS.
> - Agent tools/reasoning = **`nemo-super`** (validated reliable; `ilmu-v3.1` is NOT — fails tool-calling/date math). Single-vendor (YTL/ILMU API), OpenAI-compatible.
> - `bge-m3` embeddings + `bge-reranker` available for semantic memory.

---

## Architecture

```
Flutter (Web/Android/iOS) ⇄ Azure Container Apps (FastAPI, MY region) ⇄ ILMU ASR/TTS API
   (bidirectional audio)        │ server-mediated streaming pipeline
                                ├─ VAD/endpointing + barge-in
                                ├─ Agent core: tool registry + execute + confirm
                                ├─ LLM layer: ILMU (default) ↔ frontier (fallback)
                                ├─ Memory inject (per-user)
                                └─ Azure Postgres (asyncpg)
                                OIDC: Google / Microsoft / Apple (login only in P1)
```

Voice path: `mic →(stream)→ VAD → ILMU ASR →(text)→ [LLM + agent] →(sentences)→ ILMU TTS →(stream)→ speaker`; user speech during playback → **barge-in** cancels TTS + LLM and starts a new turn.

- **No Supabase, no PWA, no email/password, no black-box realtime model as primary, no WhatsApp scraping.**
- **Server-mediated:** client audio streams through our server; tools execute server-side; memory injected; usage metered.
- Multi-tenant from day one — keyed by `user_id` / connection, no globals.
- OpenAI Realtime kept only as an optional A/B comparison harness.

---

## Build order

| # | Step | Files | Notes |
|---|------|-------|-------|
| 0 | **Spikes** | `spikes/` | ILMU capability + LLM tool-calling bake-off (gating) |
| 1 | **DB + migrations** | `server/migrations/` | yoyo SQL: `users`, `provider_accounts`, `refresh_tokens`, `conversations`, `messages`, `memories` (tsvector), `action_log`, `usage_log` |
| 2 | **DB layer** | `server/app/db.py`, `config.py` | asyncpg pool; run/verify migrations on startup |
| 3 | **Auth — OIDC RP + sessions** | `server/app/auth/` | Verify provider `id_token`; mint our JWT (access+refresh); refresh rotation; account-collision → confirm-link. Identity scopes only in P1 |
| 4 | **WebSocket hub** | `server/app/ws.py`, `main.py` | `/ws`; authenticate our JWT on connect; per-user session; no globals |
| 5 | **VAD + endpointing** | `server/app/voice/vad.py` | Server-side VAD (Silero); detect speech start/end; drives turn-taking + barge-in |
| 6 | **ILMU ASR (batch)** | `server/app/voice/asr.py` | On VAD endpoint, POST utterance file → final transcript (`StreamingASR` impl, no partials) |
| 7 | **LLM layer + agent core** | `server/app/agent/` | LLM abstraction (`nemo-super` for tools; `ilmu-v3.1` for Manglish gen); tool registry (`auto`/`confirm`), execution, confirmation gating |
| 8 | **ILMU TTS (per-sentence)** | `server/app/voice/tts.py` | Sentence-chunk LLM output → POST each sentence → play back-to-back (`StreamingTTS` impl) |
| 9 | **Pipeline orchestration** | `server/app/voice/pipeline.py` | Wire asr→llm→tts; handle barge-in cancel; meter voice-seconds |
| 10 | **Foundational tools** | `server/app/agent/tools/` | `remember`, `recall`, `current_time`, `web_lookup` |
| 11 | **Memory + prompts** | `server/app/memory.py`, `prompts.py` | tsvector recall, auto-extract, 30-min resume; **Manglish** personality; memory injected per session |
| 12 | **Flutter scaffold** | `app/lib/` | Riverpod (auth, voice, orb, convo); `flutter_secure_storage`; SSO |
| 13 | **Streaming audio client** | `app/lib/voice/`, `audio/` | Bidirectional streaming capture + playback; barge-in; show transcript + EDITH text |
| 14 | **Orb** | `app/lib/orb/` | GLSL fragment shader via `FragmentProgram`; amplitude uniform from the live stream |
| 15 | **Auth + onboarding UI** | `app/lib/auth/`, `onboarding/` | SSO buttons; mic permission; EDITH intro (auto-speaks); first conversation |
| 16 | **Deploy** | `Dockerfile`, CI | Server → Azure Container Apps (MY region); Flutter web → static host; mobile → TestFlight / Play beta |

---

## Auth flow (OIDC, login-only in Phase 1)

1. Client runs provider sign-in → receives an `id_token`.
2. Client → `POST /auth/{provider}`.
3. Server verifies `id_token` (issuer, audience, signature via JWKS), extracts subject + email.
4. Finds/creates `users` + `provider_accounts` (identity scopes only). Existing verified email on another account → `link_required`; client prompts to confirm linking.
5. Server issues access JWT + refresh token (hashed in `refresh_tokens`).
6. Client stores tokens (`flutter_secure_storage` mobile; IndexedDB web); opens WebSocket.
7. WS auth: first message `{"type":"auth","token":"<our access JWT>"}`.

Refresh: `POST /auth/refresh` (rotates). Logout: `POST /auth/logout` (revokes).

---

## WebSocket / streaming protocol

Continuous bidirectional stream over `/ws` (not turn-based request/response).

### Client → Server
| Type | Format | Description |
|------|--------|-------------|
| `auth` | `{"type":"auth","token":"<our JWT>"}` | First message |
| binary | raw audio frames | Continuous mic audio |
| `text` | `{"type":"text","content":"..."}` | Optional typed input |
| `confirm` | `{"type":"confirm","action_id":"...","ok":true}` | Answer a pending confirmation |

*(Barge-in is detected server-side by VAD; the client just keeps streaming mic audio. A client `{"type":"barge_in"}` hint may be sent if client-side VAD fires first.)*

### Server → Client
| Type | Format | Description |
|------|--------|-------------|
| `auth_ok` | `{"type":"auth_ok","user":{...}}` | Auth succeeded |
| `error` | `{"type":"error","code":"...","message":"..."}` | Error |
| `status` | `{"type":"status","state":"listening\|thinking\|speaking\|idle"}` | Drives orb |
| `transcript` | `{"type":"transcript","role":"user\|edith","text":"...","final":bool}` | Live transcript (both sides) |
| audio | binary frames | EDITH's streamed speech |
| `confirm_request` | `{"type":"confirm_request","action_id":"...","summary":"Reply Ian 'I'll be late' — send?"}` | Agent needs a yes before a `confirm` action |
| `tool_event` | `{"type":"tool_event","name":"...","state":"running\|done"}` | Optional UI hint |

---

## Agent core (Phase 1)

- **LLM layer:** single interface; **`nemo-super`** for agentic/tool turns (spike-validated), `ilmu-v3.1` for Manglish generation. Frontier (Claude/GPT) is an optional escape hatch only. All via the OpenAI-compatible ILMU API.
- **Tool registry:** each tool declares name, JSON schema, and class — `auto` (run immediately) or `confirm` (require `confirm_request` → `confirm`).
- **Execution:** model emits a function call → pipeline runs it server-side → result fed back → EDITH speaks the outcome.
- **Confirmation:** `confirm` tools emit `confirm_request` and pause; `ok:false` skips and EDITH acknowledges.
- **P1 tools:** `remember`, `recall`, `current_time`, `web_lookup` (all `auto`), plus one deliberately gated demo tool to prove the confirm path before Phase 2 writes.
- **Action log:** every executed action recorded in `action_log`.

---

## Database schema (Phase 1)

```sql
users            (id UUID PK, display_name, primary_email, preferred_voice,
                  language_pref, timezone, onboarded, created_at)
provider_accounts(id UUID PK, user_id FK, provider, provider_subject, email,
                  scopes, access_token_enc, refresh_token_enc, token_expiry,
                  created_at)            -- identity in P1; API tokens in P2
refresh_tokens   (id UUID PK, user_id FK, token_hash, expires_at, revoked,
                  created_at)
conversations    (id UUID PK, user_id FK, started_at, ended_at, summary)
messages         (id BIGSERIAL PK, conversation_id FK, user_id FK, role, content,
                  created_at)
memories         (id BIGSERIAL PK, user_id FK, type, content, source, importance,
                  search_vector tsvector, created_at)
action_log       (id BIGSERIAL PK, user_id FK, tool, args_summary, result,
                  created_at)
usage_log        (id BIGSERIAL PK, user_id FK, call_type, voice_seconds,
                  input_tokens, output_tokens, created_at)
```

OAuth API tokens (`*_enc`) encrypted at rest. P1 stores identity-scope accounts only.

---

## Tech stack

- **Backend:** Python 3.12, FastAPI, asyncpg, httpx, yoyo-migrations; server-side VAD (Silero)
- **Voice:** ILMU ASR + TTS (file/batch, OpenAI-compatible API), server-mediated turn-based pipeline (per-sentence TTS)
- **Agent LLM:** `nemo-super` (tools/reasoning) + `ilmu-v3.1` (Manglish gen) — single-vendor (YTL); frontier optional escape hatch
- **Frontend:** Flutter (Dart), Riverpod, GLSL shader, streaming audio, `flutter_secure_storage`
- **Auth:** self-hosted OIDC relying party (Google/Microsoft/Apple) + own JWT sessions
- **DB:** Azure Database for PostgreSQL · **Hosting:** Azure Container Apps (MY region)

---

## Verification checklist

- [ ] ILMU + LLM spikes pass before building around them
- [ ] Sign in with each provider on web + mobile; account-collision linking works
- [ ] Real-time BM/Manglish voice-to-voice, low latency; barge-in interrupts cleanly
- [ ] Conversation mirrored as on-screen text (both sides)
- [ ] Agent executes an `auto` tool; a `confirm` tool pauses for a yes
- [ ] Memory persists and is recalled across sessions
- [ ] Orb at 60fps from the live stream; per-user voice-minute metering correct
- [ ] 10+ concurrent users, no cross-user data leakage
- [ ] Onboarding completes end-to-end
