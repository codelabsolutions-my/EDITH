"""FastAPI application factory.

On startup: configure logging, validate required config, apply DB migrations, and
open the asyncpg pool (stored on ``app.state.db_pool``). Connectors self-register
via discovery. A failure applying migrations blocks startup — fail fast over
serving against a half-built schema.

The app is runnable **without** a reachable database (the WebSocket falls back to
in-memory storage) so the text agent and tests work offline; when ``EDITH_REQUIRE_DB``
is unset we log and continue rather than abort if the pool can't connect.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import agent  # noqa: F401 — ensure the agent package is importable
from .auth import router as auth_router
from .config import get_settings
from .connectors import examples
from .connectors.registry import registry
from .db import Database, apply_migrations
from .integrations.router import router as integrations_router
from .logging_config import configure_logging, get_logger
from .ws import router as ws_router

log = get_logger("edith.main")


def discover_connectors() -> None:
    """Import connector modules so they register with the default registry."""
    registry.discover(examples)
    from .agent import tools

    registry.discover(tools)
    # Built-in service connectors that live as single modules (not a package).
    from .connectors import gmail, google_calendar  # noqa: F401 — @register runs on import


async def _startup_db(app: FastAPI) -> Database | None:
    """Apply migrations and open the pool. Returns None if the DB is unreachable."""
    settings = get_settings()
    require_db = os.getenv("EDITH_REQUIRE_DB", "").lower() in ("1", "true", "yes")
    try:
        apply_migrations(settings.DATABASE_URL)
        db = Database(settings.DATABASE_URL)
        await db.connect()
        app.state.db_pool = db.pool
        return db
    except Exception:
        if require_db:
            raise
        log.warning("database unavailable — running with in-memory storage")
        app.state.db_pool = None
        return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.LOG_LEVEL, json=settings.is_production)
    settings.require_runtime()
    discover_connectors()
    db = await _startup_db(app)
    try:
        yield
    finally:
        if db is not None:
            await db.close()


def create_app() -> FastAPI:
    # Discover connectors eagerly too, so create_app() without lifespan (tests using
    # TestClient without a context manager) still has the tool registry populated.
    discover_connectors()
    app = FastAPI(title="EDITH", version="0.0.0", lifespan=lifespan)
    app.state.db_pool = None
    app.include_router(auth_router)
    app.include_router(integrations_router)
    app.include_router(ws_router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


# Configure baseline logging at import so module-level logs are formatted even
# before lifespan runs (e.g. under `uvicorn app.main:app`).
configure_logging(level=logging.getLevelName(logging.INFO).lower(), json=False)
app = create_app()
