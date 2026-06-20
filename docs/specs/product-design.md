# EDITH — Product Design Spec

> **E**veryday **D**igital **I**ntelligent **T**ask **H**elper
>
> A voice-first AI **agent** for Malaysia — speaks your language (BM + Manglish), and actually gets things done.
> Inspired by JARVIS (cited as origin project).

---

## Vision

Most people don't use AI because it's intimidating — type prompts, learn interfaces, and it doesn't even speak the way they do. EDITH removes all of that. You just talk — in **Bahasa Malaysia, English, or the Manglish mix everyone actually uses** — and EDITH *does things*: manages your calendar and email, handles messages, remembers your life, and nudges you proactively. Not a chatbot that answers; an assistant that handles.

**Target user:** Non-technical Malaysians who'd benefit from AI but find Siri / ChatGPT / Alexa too complex, too foreign, or too poor at local language and context. Busy parents, small business owners, older adults, professionals who just want things handled.

**Positioning:** "The AI assistant that actually helps — and actually understands you." A local-language voice agent that beats foreign assistants on Malaysian language, accent, and context.

---

## The EDITH experience (north-star flow)

1. **Get EDITH** — open the web app to try instantly, or install the Android/iOS app for the full experience.
2. **Sign in** — one tap with Google, Microsoft, or Apple. No passwords.
3. **Link your apps** — a connection hub lets you choose what EDITH can access (email, calendar, contacts, WhatsApp on Android…). Each is explicit, revocable, requested just-in-time.
4. **Just talk** — tap and speak naturally in BM/English/Manglish. EDITH talks back in **real time** (you can interrupt mid-sentence), with the conversation also shown **on screen as text**.
5. **It acts** — "reply Ian I'll be late" / "move my 3pm to 4 and tell the team" → EDITH does it, confirming before anything irreversible.
6. **It's proactive** — "Ian messaged you an hour ago and you haven't replied" arrives as a tap-to-engage notification.
7. **Invoke instantly (mobile)** — a home-screen **widget / quick-action** lets you talk without opening the app.

**Response model:** real-time **voice-to-voice** (speech in, speech out, barge-in), always mirrored as on-screen text. Mute audio and read, or run hands-free.

---

## Product model

- **Native cross-platform clients (Flutter)** — Android + iOS + Web at launch; Mac/Windows desktop later. One Dart codebase; thin native layers (platform channels) for widgets, quick actions, wake-word, and Android WhatsApp assist.
- **Web is the trial surface** — instant "tap and talk." Ambient + device features (widget, background invocation, wake-word, WhatsApp) are mobile/native only.
- **Cloud backend on Azure**, hosted **in/near Malaysia** (Azure Southeast Asia / Malaysia region) for low latency to users and the ILMU voice API.
- **EDITH is an agent** — a tool-calling LLM that picks integrations, chains steps, confirms risky actions, reports back — from day one.
- **Integration hub** — connect apps via OAuth (Google, Microsoft, …), scopes requested incrementally per feature.
- **Optional local agent (later)** — Mac/PC companion for device-only capabilities.
- **Free tier** — limited daily voice minutes. **Paid tiers** — more minutes, premium voices, full integrations, proactivity.

---

## Voice & agent architecture

EDITH uses a **streaming componentized pipeline** (not a single black-box speech model) so we get local-language quality, cost control, and full agent control:

```
mic ─(stream)→ VAD/endpoint ─→ ILMU ASR ─(partial+final text)→ [ LLM + agent core ] ─(sentences)→ ILMU TTS ─(stream)→ speaker
        ▲ barge-in: user speech during playback cancels TTS + LLM, starts a new turn         tools · confirm · memory
```

- **ASR + TTS = ILMU** — chosen because it's **trained for Bahasa Malaysia + Manglish code-switching**, which foreign models handle poorly. Accessed via ILMU's **managed API** (pending the Phase-1 spike to confirm streaming support, latency, code-switching accuracy, and cost).
- **Reasoning LLM = ILMU by default, swappable.** ILMU's LLM is the default (Manglish-native). The provider abstraction lets us **fall back to a frontier model (Claude/GPT)** — and the **fallback trigger is *tool-calling reliability***, not general quality: speaking great Manglish and emitting correct, consistent function calls are different competencies. If ILMU nails language but fumbles tool-calls, we route agentic turns to the frontier model.
- **Server-mediated, always** — client audio flows through our server. Tools, memory injection, confirmation, keys, and metering live server-side.
- **Agent core from day one** — a tool registry + server-side execution + confirmation gating ships in Phase 1 (foundational tools: memory, time, web). Owning the LLM turn makes function-calling, confirmation, and memory first-class.
- **Conversational quality is engineered, not free** — streaming ASR, server-side **VAD** (e.g. Silero) + endpointing, sentence-chunked streaming TTS, and **barge-in cancellation** are a Phase-1 workstream.
- **Comparison harness** — OpenAI Realtime stays optionally wired so we can A/B the *feel* and keep a fallback if ILMU's streaming/latency disappoints.

---

## Trust & confirmation model (cross-cutting)

Confirmation is designed **once** and applied to **every** tool, not per-integration.

- **Auto-execute** reversible/local/read actions: read calendar/mail, draft a reply, add a to-do, set a reminder, summarize.
- **Confirm verbally before** external or hard-to-undo actions: send email, send a WhatsApp reply, delete an event, modify others' meetings, unlock a door, post anywhere. EDITH states the action and waits ("Reply to Ian, 'I'll be late' — send?").
- **Per-action/integration overrides** (a tunable "trust posture") come later; the default ships first.
- Every action is **logged** (`action_log`) and undoable where the API allows.

Each tool declares its class (`auto` / `confirm`); the agent core enforces it.

---

## Integration catalog & feasibility

Tiered honestly by how cleanly each can be accessed.

| Integration | Access path | Feasibility | Phase |
|-------------|-------------|-------------|-------|
| Google Calendar | Google OAuth | ✅ Clean cloud API | 2 |
| Gmail | Google OAuth (CASA review) | ✅ Clean (restricted-scope review) | 2 |
| Microsoft Outlook (mail+cal) | Microsoft Graph | ✅ Clean cloud API | 2 |
| Contacts / phone book | Google People / MS Graph / device-native | ✅ Cloud or device | 2 |
| **WhatsApp — personal assist** | **Android on-device:** NotificationListenerService (read) + notification direct-reply / RemoteInput (send) | ✅ On-device, official Android APIs · **Android only (iOS can't)** | 4 |
| **WhatsApp — EDITH's own number** | **WhatsApp Business Cloud API** (dedicated number; users DM/voice-note EDITH, forward, groups) | ✅ Compliant · cost-gated (per-conversation fees) | separate track |
| Notes / tasks | Notion / Google Tasks / Todoist / MS To Do | ⚠️ Per-provider | 3 |
| SMS / iMessage | No cloud API; Android SMS native; iMessage via local Mac agent | ⚠️ Device/agent-side only | 5 |
| Social media | Heavily restricted APIs; DM access generally unavailable | ❌ Mostly deferred | TBD |
| Smart home | Google Home/Alexa cloud; HomeKit via local agent | ⚠️ Cloud / agent | 5 |

### WhatsApp — the two tracks (deliberately separate)

WhatsApp is dominant in Malaysia, so it gets real attention — but split by what's *actually* possible:

- **Personal assist (Android, on-device).** Powers scenarios like *"Ian messaged you and you haven't replied"* and *"reply Ian I'll be late."* Uses Android's **NotificationListenerService** to read incoming WhatsApp notifications and the notification's **direct-reply (RemoteInput)** action to send — all on the user's own phone, via official Android OS APIs. **No server-side WhatsApp Web scraping** (which risks getting users' numbers banned, violates ToS, and is a security liability) and **zero per-message cost**. Opt-in. **Not possible on iOS** (Apple sandbox forbids notification-read / programmatic send) — stated plainly. Limited to notified messages going forward; partial group/media handling.
- **EDITH's own number (Business API).** A separate, optional **zero-install** channel: EDITH owns a dedicated number via the compliant WhatsApp Business Cloud API; users **text or voice-note EDITH directly** (ILMU ASR on the voice note → reason → ILMU TTS reply), forward messages, or add EDITH to a group. Huge Malaysian reach + an acquisition funnel into the app. Gated on per-conversation cost; rolled out when the economics fit.

**Principle:** never promise access we can't deliver officially; never put users' primary accounts at ban risk.

---

## Auth & identity design

- **Providers:** Google, Microsoft, Apple via OpenID Connect.
- **Sessions:** verify provider `id_token`, then mint our own JWT access (short-lived) + refresh (stored hashed, revocable).
- **Incremental authorization:** identity scopes at login; API scopes requested just-in-time per feature, reusing the same provider credential (Google/Microsoft).
- **Apple is identity-only** (no cloud calendar/mail API; required on iOS once other social login is offered).
- **Account collision → confirm-and-link** (one user → many provider accounts).

---

## Roadmap

### Phase 1 — Foundation + Agent Core
**Goal:** sign in, talk to EDITH in real-time voice-to-voice (BM/Manglish), and have it act via a tool-calling agent with memory.
- SSO sign-in (Google/Microsoft/Apple)
- ILMU streaming pipeline (ASR → LLM → TTS), server-mediated, **VAD + barge-in**, voice + on-screen text
- **Agent core:** tool registry, execution, confirmation gating; foundational tools (memory, time, web)
- Per-user memory; Manglish personality
- GLSL-shader orb driven by the live stream
- Per-user voice-minute metering
- **De-risk spikes (gating):** (a) ILMU capability — streaming, latency, code-switching accuracy, cost, licensing; (b) LLM bake-off — ILMU vs frontier on Manglish reasoning **+ tool-calling reliability**

### Phase 2 — The Wedge (Calendar + Email + Contacts)
- Integration hub + incremental OAuth (Google + Microsoft)
- Tools: read/write calendar; read/summarize/draft/**send (confirmed)** email; resolve contacts

### Phase 3 — Proactivity
- Background scheduler + workers; **push (FCM/APNs), tap-to-engage**; quiet hours + frequency caps
- Daily briefing, meeting nudges, unreplied-message prompts, departure alerts; voice-defined automations

### Phase 4 — Ambient invocation & WhatsApp (Android)
- iOS: widget / Control Center / App Intents / Action Button → press-to-talk; Android: App Widget / Quick Settings tile → press-to-talk
- **WhatsApp personal assist (Android on-device):** read unreplied messages + send replies via notification APIs
- Then **on-device wake word** ("Hey EDITH")

### Phase 5 — Reach
- Smart home (Google Home/Alexa cloud; HomeKit via local agent); Flutter desktop (Mac/Windows); local agent (iMessage/SMS, desktop control)

### Phase 6 — Growth & Monetization
- **Free:** limited daily voice minutes · basic calendar read
- **Pro (RM-priced):** more minutes · full calendar + email · automations · premium voices · WhatsApp assist
- **Team/Family:** multi-user · shared calendar awareness
- **WhatsApp Business "own number" channel** as a growth/acquisition track when cost-justified
- Cost controls; Stripe billing (supports MY)

---

## Cost note (designed for, not deferred)

A streaming pipeline with ILMU (especially if cost-efficient/local) should be **materially cheaper per minute than a black-box realtime model**, which helps free-tier economics. Still:
- Free tier is **time-based** (voice-minutes/day), not "N interactions."
- **Per-user metering** ships in Phase 1.
- WhatsApp **personal assist** is on-device → **zero marginal cost**; the **Business-API channel** has per-conversation fees → gated behind clear ROI.

---

## Data & privacy

| Data | Storage | User control |
|------|---------|--------------|
| Conversations | Azure Postgres (encrypted) | Delete anytime |
| Memories/preferences | Azure Postgres (encrypted) | View, edit, delete |
| OAuth tokens | Azure Postgres, **encrypted at rest** | Revoke per-integration |
| Calendar/email content | On-demand via OAuth, **not stored** | Revoke anytime |
| WhatsApp (Android assist) | Read **on-device**; only what EDITH acts on leaves the phone | Permission revocable in Android settings |
| Voice audio | Streamed for inference, **not stored** | N/A |
| Action log | Azure Postgres | View; undo where supported |
| Payment | Stripe (never on our servers) | Stripe portal |

**Commitments:** voice audio not retained; third-party content accessed on-demand, not cached; on-device WhatsApp data stays on the device except actioned items; export + delete all data; no data sold; SOC 2 target.

---

## Repo structure

```
edith/
├── server/                       # FastAPI (Python 3.12)
│   ├── app/
│   │   ├── main.py  ws.py        # app + WebSocket hub (/ws), per-user sessions
│   │   ├── voice/                # streaming pipeline
│   │   │   ├── asr.py            #   ILMU ASR (streaming)
│   │   │   ├── tts.py            #   ILMU TTS (streaming)
│   │   │   ├── vad.py            #   VAD + endpointing
│   │   │   ├── pipeline.py       #   orchestrates asr→llm→tts + barge-in
│   │   │   └── realtime_compat.py#   optional OpenAI Realtime A/B harness
│   │   ├── agent/                # tool-calling core
│   │   │   ├── llm.py            #   LLM abstraction (ILMU default, frontier fallback)
│   │   │   ├── registry.py  execute.py  confirm.py
│   │   │   └── tools/            #   memory, time, web (P1); calendar/email (P2)
│   │   ├── auth/                 # OIDC RP + JWT sessions + linking
│   │   ├── integrations/         # OAuth connectors (Google, Microsoft) — P2
│   │   ├── proactivity/          # scheduler, workers, push — P3
│   │   ├── memory.py  prompts.py  db.py  config.py
│   ├── migrations/               # yoyo plain-SQL
│   ├── tests/  Dockerfile  pyproject.toml
├── app/                          # Flutter (web + android + ios)
│   ├── lib/
│   │   ├── main.dart
│   │   ├── state/                # Riverpod (auth, voice, orb, convo)
│   │   ├── voice/  audio/        # streaming bidirectional audio + barge-in
│   │   ├── orb/                  # GLSL fragment-shader orb
│   │   ├── auth/  linking/  onboarding/
│   ├── android/                  # native: NotificationListener + reply (WhatsApp), widget
│   ├── ios/  web/                # platform shells
│   └── pubspec.yaml
├── docs/specs/                   # product-design.md, phase-1-mvp.md
├── docker-compose.yml            # local dev: server + postgres
└── .env.example
```

---

## Tech stack

- **Client:** Flutter (Dart), Riverpod, GLSL shader orb, streaming audio, `flutter_secure_storage`; Android native (NotificationListenerService + RemoteInput) for WhatsApp assist
- **Backend:** Python 3.12, FastAPI, asyncpg, httpx, yoyo-migrations
- **Voice:** **ILMU ASR + TTS** (managed API) · server-side VAD (Silero) · streaming pipeline · OpenAI Realtime (optional A/B harness)
- **Agent LLM:** ILMU LLM (default) ↔ frontier (Claude/GPT) fallback, behind a provider abstraction; trigger = tool-calling reliability
- **Auth:** self-hosted OIDC relying party (Google/Microsoft/Apple) + own JWT sessions
- **DB:** Azure Database for PostgreSQL (`tsvector` memory FTS)
- **Hosting:** Azure Container Apps, **Southeast Asia / Malaysia region**; static host (web); TestFlight/Play (mobile)
- **Push:** FCM / APNs (Phase 3) · **CI/CD:** GitHub Actions

---

## What carries over from JARVIS (cited)

| JARVIS component | EDITH equivalent | Adaptation |
|-----------------|------------------|------------|
| `server.py` WebSocket | `server/app/ws.py` + `voice/` | Multi-user, streaming pipeline, our-JWT auth, no globals |
| `llm_config.py` | `server/app/agent/`, `prompts.py` | Tool-calling agent; ILMU default; Manglish personality |
| `memory.py` (SQLite) | `server/app/memory.py` (Postgres) | Multi-tenant, asyncpg, tsvector |
| `frontend/src/orb.ts` | `app/lib/orb/` (GLSL) | Reimplemented for Flutter; driven by live stream |
| `frontend/src/voice.ts` | `app/lib/voice/`, `audio/` | Streaming bidirectional audio + barge-in |
| Personality/prompts | `server/app/prompts.py` | EDITH's Manglish voice; conciseness preserved |

---

## Verification plan

### Phase 1
- [ ] **Spikes pass:** ILMU streaming/latency/code-switching/cost acceptable; chosen LLM reliable at tool-calling
- [ ] Sign in (Google/Microsoft/Apple) web + mobile; account-collision linking works
- [ ] Real-time BM/Manglish voice-to-voice, low latency; **barge-in** interrupts cleanly; reply mirrored as text
- [ ] Agent runs an `auto` tool mid-conversation; a `confirm` tool waits for yes
- [ ] Memory persists across sessions; orb at 60fps; per-user minute metering correct
- [ ] 10+ concurrent users, no cross-user leakage

### Phase 2
- [ ] Just-in-time OAuth upgrade; "what's my schedule?" real events; "send email" requires + respects confirmation

### Phase 3
- [ ] Scheduled trigger → tap-to-engage push; quiet hours respected

### Phase 4
- [ ] Widget/quick-action → listening; wake word on-device
- [ ] **Android:** "Ian messaged you, unreplied" surfaced; "reply Ian I'll be late" sends via notification API (confirmed); iOS correctly shows feature unavailable

### Phase 5
- [ ] Smart-home device controlled; desktop app on Mac+Windows; local agent connects

### Phase 6
- [ ] Free-tier minute limiting; Stripe checkout + subscription; (Business-API channel pilot if launched)
