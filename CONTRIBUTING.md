# Contributing to EDITH

Thanks for your interest in contributing! EDITH is open-core under
[Apache-2.0](LICENSE), and community **connectors** are a first-class way to help.

By participating you agree to our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Developer Certificate of Origin (DCO)

We accept contributions under the [DCO](https://developercertificate.org/) — a
lightweight statement that you wrote the patch or otherwise have the right to
submit it under our license. **There is no CLA to sign.**

You assert the DCO by signing off every commit:

```bash
git commit -s -m "feat(connectors): add Todoist connector"
```

This appends a trailer to your commit message:

```
Signed-off-by: Your Name <your.email@example.com>
```

Use the same name/email as your GitHub account. The DCO check in CI will fail PRs
with unsigned commits. To sign off commits you already made:

```bash
git rebase --signoff main
```

---

## Ways to contribute

- 🔌 **Connectors** — integrate a third-party service. Start with the
  [connector cookbook](server/app/connectors/README.md). This is the most
  impactful contribution and the path we've optimized for.
- 🐛 **Bug fixes** — find an issue, comment that you're on it, send a PR.
- ✨ **Features** — open a discussion/issue first for anything non-trivial so we
  can align on design before you build.
- 📖 **Docs** — improvements to specs, guides, and examples are always welcome.

## Development setup

```bash
cp .env.example .env          # fill in credentials
make setup                    # install dev tooling + pre-commit hooks
make dev                      # server + postgres (docker-compose)
make test                     # run all tests
make lint                     # ruff + mypy + flutter analyze
make fmt                      # auto-format (ruff format + dart format)
```

- **Server** (`server/`): Python 3.12, FastAPI, asyncpg. Tooling: `ruff`
  (lint + format), `mypy` (types), `pytest` (tests).
- **App** (`app/`): Flutter/Dart. Tooling: `flutter analyze`, `dart format`,
  `flutter test`.

Install [pre-commit](https://pre-commit.com/) hooks once (done by `make setup`) so
formatting and lint run automatically before each commit.

## Branching & PR workflow

- Branch from `main`: `feat/...`, `fix/...`, `docs/...`, `connector/...`.
- Keep PRs focused and reasonably small. One connector per PR.
- Ensure `make lint test` passes locally; CI must be green.
- Fill in the PR template, including the DCO checkbox.
- A maintainer reviews; connectors also get a
  [security review](SECURITY.md#connector-security-model).

## Commit conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <summary>

type: feat | fix | docs | refactor | test | chore | perf | ci
```

Examples: `feat(agent): add confirmation gating`,
`fix(auth): rotate refresh token on reuse`,
`feat(connectors): add Google Calendar connector`.

## Code style

- **Python:** typed (`mypy` strict-ish), `ruff`-formatted, async-first. Public
  functions/classes get docstrings. No ORM — raw SQL via asyncpg.
- **Dart:** follow `flutter analyze` (lints in `app/analysis_options.yaml`);
  `dart format` enforced.
- Prefer clear names over comments; comment the *why*, not the *what*.
- Match the style of surrounding code.

## What not to put in this repo

EDITH is **open-core**. Billing, multi-tenant cloud operations, and internal
infra live in a separate private repo and are git-ignored here. Don't add
proprietary cloud-ops code or secrets to this repository.

## Questions

Open a [Discussion](../../discussions) or a `question` issue. Thank you for
helping build EDITH! 🙌
