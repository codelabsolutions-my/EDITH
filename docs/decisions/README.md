# Architecture Decision Records (ADRs)

Short, immutable records of significant, hard-to-reverse decisions — so future
contributors understand the *why*, not just the *what*.

- Add an ADR for any choice you'd want explained a year from now (a framework, a
  protocol, a vendor, a boundary).
- Number them sequentially: `NNNN-short-title.md`. Copy
  [`0000-template.md`](0000-template.md).
- ADRs are **append-only**: don't rewrite history. To change a decision, add a
  new ADR that supersedes the old one (and mark the old one `Superseded by NNNN`).

## Log

| # | Title | Status |
|---|-------|--------|
| [0001](0001-open-core-apache-2.0.md) | Open-core model under Apache-2.0 | Accepted |

> Decisions still to backfill as ADRs: ILMU streaming voice pipeline (vs. realtime
> speech-to-speech); Flutter clients (vs. PWA / native); self-hosted SSO + Azure
> Postgres (vs. Supabase); agent-core-from-day-one.
