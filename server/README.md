# EDITH server

FastAPI backend: the agent core, voice pipeline, auth, and the **connector
framework**. Python 3.12, asyncpg (no ORM), Azure Postgres.

See [`docs/specs/phase-1-mvp.md`](../docs/specs/phase-1-mvp.md) for the build plan.

## Layout

```
app/
  connectors/      Connector framework + examples  (community-contributed)
  agent/           Tool registry, execution, confirmation, LLM layer   (planned)
  voice/           ILMU ASR/TTS streaming pipeline + VAD/barge-in       (planned)
  auth/            OIDC relying party + JWT sessions                     (planned)
  integrations/    OAuth connectors (Google, Microsoft)                 (planned)
  ...
migrations/        yoyo plain-SQL migrations
tests/             pytest (incl. connector conformance)
```

## Develop

```bash
uv sync --all-extras --dev     # or: pip install -e ".[dev]"
make -C .. test-connectors     # run the connector conformance suite
make -C .. lint                # ruff + mypy
```

Want to add an integration? Read
[`app/connectors/README.md`](app/connectors/README.md).
