# 0001. Open-core model under Apache-2.0

- **Status:** Accepted
- **Date:** 2026-06-20
- **Deciders:** Core team

## Context

EDITH is a commercial product, but we want a public repo so the community can
contribute **connectors** (integrations), and so we gain trust and third-party
security review. We need a licensing + repository model that maximizes
contribution and adoption while keeping the business defensible.

## Decision

Adopt an **open-core** model with the public repo licensed **Apache-2.0**:

- The public repo holds the runnable core: agent, voice pipeline, auth, the
  **connector framework**, and the Flutter app.
- Proprietary cloud-only pieces (billing, cloud-ops, premium features) live in a
  separate **private** repo that layers on top of the public core.
- Contributions are accepted under the **DCO** (no CLA), consistent with a
  permissive license.

## Alternatives considered

- **AGPL-3.0 + CLA** — stronger protection against closed cloud forks and enables
  dual-licensing, but adds contributor friction (CLA) and some orgs avoid AGPL.
  Rejected: for a voice assistant the moat is the hosted service, data/memory
  network effects, distribution, and ILMU/local-language quality — not the source
  — so the "someone hosts a competing fork" risk is acceptable early.
- **BSL-1.1 (source-available)** — strongest business protection, but not
  OSI-"open source"; deters some contributors. Rejected for the same reason:
  maximizing contribution matters more than source-level protection here.
- **Connectors-only public** — narrowest, but contributors can't run the full app
  to develop/test connectors. Rejected.

## Consequences

- Maximum goodwill and the lowest barrier to connector contributions.
- We rely on the license + business model (not code secrecy) for defensibility.
- Requires discipline to keep a clean **extension seam** so private features layer
  on without forking core (see `docs/engineering.md`).
- A competitor *could* run a hosted EDITH from the public core; accepted risk.
