"""FastAPI application factory.

On startup, discover all connectors (examples + the built-in foundational tools)
so they self-register into the shared registry before any session runs.
"""

from __future__ import annotations

from fastapi import FastAPI

from . import agent  # noqa: F401 — ensure the agent package is importable
from .connectors import examples
from .connectors.registry import registry
from .ws import router as ws_router


def discover_connectors() -> None:
    """Import connector modules so they register with the default registry."""
    registry.discover(examples)
    # The foundational tools live under agent.tools; import the package and
    # discover its modules the same way.
    from .agent import tools

    registry.discover(tools)


def create_app() -> FastAPI:
    app = FastAPI(title="EDITH", version="0.0.0")
    discover_connectors()
    app.include_router(ws_router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
