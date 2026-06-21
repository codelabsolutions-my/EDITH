"""CORS: the browser client's cross-origin preflight must succeed."""

from __future__ import annotations

from app.main import create_app
from fastapi.testclient import TestClient


def test_preflight_options_is_allowed() -> None:
    client = TestClient(create_app())
    # A CORS preflight for the dev-login POST (what the Flutter web app triggers).
    resp = client.options(
        "/auth/dev-login",
        headers={
            "Origin": "http://localhost:8080",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] in ("*", "http://localhost:8080")


def test_actual_post_carries_cors_header() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/auth/dev-login",
        json={"email": "x@example.com"},
        headers={"Origin": "http://localhost:8080"},
    )
    # 200 (DB up) or 503 (DB down) — either way the CORS header must be present.
    assert "access-control-allow-origin" in resp.headers
