# Engineering practices

How we build EDITH. This complements [`CONTRIBUTING.md`](../CONTRIBUTING.md)
(contributor mechanics) and [`SECURITY.md`](../SECURITY.md) (security + connector
review). Conventions here apply to maintainers and contributors alike.

---

## Repository model — open-core

EDITH is **open-core**. The split is **public-core vs private-cloud** — *not*
"connectors vs logic."

```
PUBLIC repo (Apache-2.0)                    PRIVATE repo (commercial)
  server/  agent · voice · auth               billing & subscriptions
           CONNECTORS live here               cloud-ops / autoscaling
  app/     Flutter client                     premium-only features
  docs/                                       infra w/ secrets
  → fully runnable & self-hostable      ◀──   → layers ON TOP of the public core
```

### What goes where

| Public (the engine) | Private (the business) |
|---|---|
| Agent core, tool framework, confirmation model | Billing, subscriptions, plan gating |
| Voice pipeline (ILMU, VAD, barge-in) | Cloud-ops, autoscaling, IaC + secrets |
| Auth (OIDC, JWT sessions) | Usage→billing metering, fraud/abuse |
| **Connectors + framework** | Premium-only features |
| Flutter app, orb, memory, base prompts | Growth/analytics internals; tuned proprietary recipes |

**Rule of thumb:** open generously. For a voice assistant the moat is the hosted
service, data/memory network effects, distribution, and local-language (ILMU)
quality — not the source. Keep private only what (1) contains secrets/ops,
(2) is premium monetization, or (3) is a genuine competitive recipe.

### Why connectors are public

Contributors must run the full app (agent, voice, auth) to develop and test a
connector. A separate connector repo only pays off at hundreds-of-connectors
scale with independent release cadences — not our situation. Keep them in the
monorepo.

### Don't split the repo yet

There is currently **no** private code. Creating a private repo now is empty
overhead. The boundary is reserved in [`.gitignore`](../.gitignore)
(`server/app/billing/`, `infra/private/`). **Spin out the private repo the day
the first proprietary feature is written** — and at that point, *layer it on top*
of the public core, never fork.

### Extension-seam principle

So the eventual public/private cut is a clean lift, not surgery:

- Premium/cloud features plug into the core through **interfaces**, not by editing
  core files. The [connector framework](../server/app/connectors/README.md) is the
  model seam — do the same for premium features.
- Core must run and be useful **without** any private modules present.
- No core file should import from a private module; dependencies point inward
  (private → public), never outward.

---

## Development workflow — spec-first

EDITH is built spec-first; this repo's history shows it. For any non-trivial
change:

1. **Plan** — agree the approach (in an issue/discussion, or with the team).
2. **Document** — write or update the relevant spec in [`docs/specs/`](specs/)
   (and `CLAUDE.md` if it changes how the system works) *before* building.
3. **Build** — implement against the spec, in small focused PRs.
4. **Verify** — tests green, lint/types clean, behavior checked.

Trivial changes (typos, small fixes) skip straight to build. The bar for "write
the spec first" is: *would another contributor need this to understand the
change?* If yes, document it.

Keep specs and `CLAUDE.md` **in sync with reality** — a stale spec is worse than
none. Update them in the same PR as the code.

---

## Quality gates

Enforced by [`pre-commit`](../.pre-commit-config.yaml) locally and
[CI](../.github/workflows/ci.yml) on every PR. See `make` targets.

| Concern | Server (Python) | App (Flutter) |
|---|---|---|
| Format | `ruff format` | `dart format` |
| Lint | `ruff check` | `flutter analyze` |
| Types | `mypy` | Dart sound types |
| Tests | `pytest` | `flutter test` |

Plus: Conventional Commits, DCO sign-off (`git commit -s`), secret scanning
(gitleaks), and connector conformance (`make test-connectors`).

---

## Testing & coverage

Policy: **ratchet, not hard-gate** — fast early, strict where it matters.

- **No CI coverage threshold** (yet). Coverage is *reported* on every PR
  (`pytest --cov`, `flutter test --coverage`), not failed. We raise an explicit
  floor as the codebase stabilizes.
- **Critical paths require tests** — reviewers enforce this. A change to any of
  these must ship with tests:
  - Auth: OIDC verification, JWT issue/refresh/rotation, account-linking
  - Agent: the **confirmation gate** (`auto` vs `confirm`), tool execution
  - Connectors: must pass the conformance suite; handlers covered by behavioural tests
  - Anything touching tokens, money, or per-user data isolation
- **Test shape:** prefer fast unit tests; add integration tests for the WebSocket
  voice path and OAuth flows. Don't write filler tests to chase a number.

Dependencies (Dependabot, weekly): review update PRs; a **new runtime dependency
needs justification** in the PR — especially in connectors (supply-chain surface).

## Logging & observability

This is an auth- and token-handling system; logging discipline is a safety
requirement, not a nicety.

- **Never log secrets or PII** — no tokens, passwords, raw audio, message/email
  contents, or full personal data. Log identifiers (`user_id`, `conversation_id`),
  not contents.
- **Structured logging** — key/value (JSON in prod), one event per line, with a
  correlation id per request/WS-session so a conversation can be traced.
- **Errors:** fail loud server-side (structured error + context), fail graceful
  user-side (a spoken/displayed apology, never a stack trace). Don't swallow
  exceptions silently.
- **Action audit:** every agent action is recorded in `action_log` (tool,
  args summary, result) — distinct from debug logs, and retained for trust/undo.

---

## Decisions

Significant, hard-to-reverse decisions (e.g. ILMU for voice, Apache-2.0,
open-core) are recorded so future contributors understand the *why*. See
[`docs/decisions/`](decisions/) (ADR log) — add an ADR for any choice you'd want
explained a year from now.
