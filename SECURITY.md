# Security Policy

EDITH handles authentication, user data, and OAuth tokens that grant access to
people's calendars, email, and messages. We take security seriously and ask the
community to do the same.

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Report privately via one of:

- GitHub [Private vulnerability reporting](../../security/advisories/new) (preferred)
- Email **security@edith.my**

Include: a description, steps to reproduce, affected component/version, and impact.
We aim to acknowledge within **3 business days** and to provide a remediation
timeline after triage. We'll credit reporters who wish to be acknowledged once a
fix ships.

## Supported versions

Until a `1.0` release, only the `main` branch is supported with security fixes.

## Scope highlights

Areas where we especially welcome scrutiny:

- Authentication / session handling (OIDC verification, JWT issuance, refresh
  rotation, account-linking)
- OAuth token storage (encryption at rest) and per-user data isolation
- The WebSocket voice path (per-user session isolation, no cross-tenant leakage)
- Connectors (see below)

---

## Connector security model

Connectors are powerful: they can hold a user's OAuth tokens and **take actions**
on their behalf. Community-contributed connectors are therefore reviewed against
the following model.

### Trust tiers

- **Official** — maintained by the core team. Shipped enabled.
- **Community** — contributed and maintained by the community. Clearly labeled as
  such in the connector hub. Reviewed before merge; users opt in explicitly.

### Requirements for every connector

1. **Least privilege.** Request the **minimum** OAuth scopes needed, and request
   them **incrementally** (just-in-time per feature), never all at signup.
2. **Correct tool classes.** Any tool that is external or hard to undo (send,
   delete, post, pay, unlock) **must** be declared `confirm`, never `auto`.
   Read/draft/reversible actions may be `auto`.
3. **No secret exfiltration.** Connectors must not log tokens, message contents,
   or PII; must not transmit user data anywhere except the connector's own
   declared third-party API.
4. **No unsafe dependencies.** New runtime dependencies are reviewed. Avoid
   network calls to undisclosed endpoints.
5. **Honor revocation.** Implement token refresh and revocation cleanly; stop
   accessing data immediately when a user disconnects.
6. **Compliance.** Only use official, ToS-compliant APIs. Connectors that scrape,
   automate unofficial clients, or risk getting users' accounts banned will **not**
   be accepted (e.g. WhatsApp Web scraping — see `docs/specs/product-design.md`).
7. **Tests.** Pass the connector conformance suite (`make test-connectors`).

### Review checklist (maintainers)

- [ ] Scopes are minimal and incremental
- [ ] `confirm`/`auto` classification is correct for every tool
- [ ] No logging/transmission of tokens, secrets, or PII
- [ ] Dependencies reviewed; no undisclosed network endpoints
- [ ] Revocation + refresh handled
- [ ] Uses official, compliant APIs only
- [ ] Conformance tests pass; trust tier labeled
