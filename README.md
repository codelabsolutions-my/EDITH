<div align="center">

# EDITH

**Everyday Digital Intelligent Task Helper**

A Malaysia-first, voice-first AI agent. Talk to it in Bahasa Malaysia, English, or
Manglish — and it actually gets things done.

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>

---

> 🚧 **Status: text + voice agent, through P5.** Running today: the tool-calling
> agent, Google OIDC login + JWT sessions, Postgres persistence, the ILMU voice
> pipeline (ASR/TTS + barge-in), **Gmail / Calendar / Contacts** over OAuth,
> **proactive reminders + push**, **WhatsApp** (Cloud API send), and **smart home**
> (Home Assistant) — with a Flutter client for web, Android, and iOS. **[Setup guide
> → `docs/SETUP.md`](docs/SETUP.md).** Monetization is the separate private layer.
> Star/watch to follow.

## What is EDITH?

EDITH is a voice-first AI **agent** for non-technical users. You sign in, talk
naturally, and EDITH takes action through the apps you already use — calendar,
email, contacts, messaging — and proactively notifies you when something needs
attention. It's built **Malaysia-first**: local-language voice quality (BM +
Manglish code-switching) is the core differentiator versus Siri, ChatGPT, and
Alexa.

- 🎙️ **Real-time voice-to-voice** — speak and be spoken to, with barge-in. Voice
  in/out via [ILMU](#) ASR/TTS, tuned for Bahasa Malaysia + Manglish.
- 🤖 **Agent from day one** — a tool-calling core that decides, acts, and confirms
  before anything irreversible.
- 🔌 **Pluggable connectors** — community-contributed integrations are first-class.
  See [Contributing a connector](#contributing-a-connector).
- 📱 **Native clients** — Flutter for Android, iOS, and Web (desktop later).
- 🔐 **Self-hosted SSO** — Google / Microsoft / Apple, no passwords; your own JWT
  sessions; OAuth tokens encrypted at rest.

Read the full design: [`docs/specs/product-design.md`](docs/specs/product-design.md)
· Phase 1 plan: [`docs/specs/phase-1-mvp.md`](docs/specs/phase-1-mvp.md).

## Architecture at a glance

```
Flutter (Web/Android/iOS) ⇄ FastAPI on Azure (MY region) ⇄ ILMU ASR/TTS
   (bidirectional audio)        │ server-mediated streaming pipeline
                                ├─ VAD/endpointing + barge-in
                                ├─ Agent core: tools + execution + confirmation
                                ├─ LLM layer: ILMU (default) ↔ frontier (fallback)
                                └─ Azure Postgres (asyncpg)
```

| Area | Choice |
|------|--------|
| Voice | ILMU ASR + TTS, streaming pipeline (server-mediated) |
| Agent LLM | ILMU default, frontier (Claude/GPT) fallback — swappable |
| Backend | Python 3.12, FastAPI, asyncpg, Azure Postgres |
| Client | Flutter (Dart), Riverpod, GLSL-shader orb |
| Auth | Self-hosted OIDC RP (Google/Microsoft/Apple) + JWT sessions |
| Hosting | Azure Container Apps, Southeast Asia / Malaysia region |

## Repository layout

```
server/    FastAPI backend — agent core, voice pipeline, auth, connectors
app/       Flutter client (web / android / ios)
docs/      Specs and engineering docs
```

> **Open-core:** this public repo holds the core server, agent, **connector
> framework**, and the app. Cloud-only operational pieces (billing, multi-tenant
> ops, internal infra) live in a separate private repository.

## Getting started

> Build tooling is being established as `server/` and `app/` are scaffolded; the
> commands below are the intended developer workflow. See
> [CONTRIBUTING.md](CONTRIBUTING.md) for the current state.

```bash
git clone https://github.com/<org>/edith.git
cd edith
cp .env.example .env          # fill in credentials
make setup                    # install dev tooling (server + app)
make dev                      # run server + postgres via docker-compose
make test                     # run the test suites
```

## Contributing a connector

A **connector** exposes a third-party service to the EDITH agent as a set of
**tools** (each marked `auto` or `confirm`). They're designed to be contributed
by the community.

1. Read the connector cookbook:
   [`server/app/connectors/README.md`](server/app/connectors/README.md).
2. Copy the example connector and adapt it.
3. Run the conformance tests: `make test-connectors`.
4. Open a PR using the **New connector** template.

Official connectors are maintained by the core team; community connectors are
clearly labeled and reviewed against the
[connector security model](SECURITY.md#connector-security-model).

## Contributing

We welcome issues and PRs. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and our
[Code of Conduct](CODE_OF_CONDUCT.md). Contributions are accepted under the
**Developer Certificate of Origin** — sign off your commits with `git commit -s`.

## Security

Found a vulnerability? Please follow [SECURITY.md](SECURITY.md) — do **not** open a
public issue for security reports.

## License

[Apache License 2.0](LICENSE) © The EDITH Authors.
