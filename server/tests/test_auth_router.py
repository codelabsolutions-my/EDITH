"""HTTP auth routes: dev-login/refresh/logout flow, OIDC fail-closed, prod guard."""

from __future__ import annotations

import asyncio

import asyncpg
from app.main import create_app
from fastapi.testclient import TestClient
from tests.conftest import TEST_DATABASE_URL, reset_db


def _reset() -> None:
    async def _go() -> None:
        pool = await asyncpg.create_pool(TEST_DATABASE_URL, min_size=1, max_size=2)
        assert pool is not None
        await reset_db(pool)
        await pool.close()

    asyncio.run(_go())


def test_dev_login_refresh_logout_flow(pg_dsn: str) -> None:
    _reset()
    app = create_app()
    with TestClient(app) as client:
        r = client.post("/auth/dev-login", json={"email": "flow@example.com", "display_name": "F"})
        assert r.status_code == 200, r.text
        tokens = r.json()
        assert tokens["access_token"] and tokens["refresh_token"]
        assert tokens["user"]["primary_email"] == "flow@example.com"

        r2 = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert r2.status_code == 200, r2.text
        rotated = r2.json()
        assert rotated["refresh_token"] != tokens["refresh_token"]

        # Logout revokes the family; the rotated token then fails.
        out = client.post("/auth/logout", json={"refresh_token": rotated["refresh_token"]})
        assert out.json() == {"ok": True}
        r3 = client.post("/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
        assert r3.status_code == 401


def test_oidc_provider_fails_closed() -> None:
    app = create_app()
    client = TestClient(app)  # no lifespan needed: fails before touching the DB
    r = client.post("/auth/google", json={"id_token": "whatever"})
    assert r.status_code == 401
    assert "not configured" in r.json()["detail"]


def test_dev_login_disabled_in_production(monkeypatch) -> None:
    import sys

    from app.config import Settings

    prod = Settings(ENV="production", JWT_SECRET="x", ILMU_API_KEY="", ILMU_API_BASE="")
    # The package re-exports the APIRouter as `router`, shadowing the submodule for
    # dotted lookups; reach the real module object via sys.modules to patch it.
    router_module = sys.modules["app.auth.router"]
    monkeypatch.setattr(router_module, "get_settings", lambda: prod)

    app = create_app()
    client = TestClient(app)
    r = client.post("/auth/dev-login", json={"email": "no@example.com"})
    assert r.status_code == 404
