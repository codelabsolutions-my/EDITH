"""End-to-end persistence: dev-login over HTTP, run a turn over WS, assert rows.

Exercises the full M1 wiring — auth issues a real JWT, the WS verifies it, and the
session records messages + action_log to Postgres. Skips if the DB is unreachable.
"""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
from app.main import create_app
from fastapi.testclient import TestClient
from tests.conftest import TEST_DATABASE_URL, reset_db


def _drain_until_turn_end(ws: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while True:
        msg = ws.receive_json()
        out.append(msg)
        if msg.get("type") == "turn_end":
            return out


def test_turn_persists_messages_and_actions(pg_dsn: str) -> None:
    # Clean slate (pg_dsn already applied migrations + ensured reachability).
    async def _reset() -> None:
        pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=2)
        assert pool is not None
        await reset_db(pool)
        await pool.close()

    asyncio.run(_reset())

    app = create_app()
    with TestClient(app) as client:  # context manager runs lifespan -> DB connects
        resp = client.post(
            "/auth/dev-login", json={"email": "persist@example.com", "display_name": "P"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        token = body["access_token"]
        user_id = body["user"]["id"]

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json()["type"] == "auth_ok"

            ws.send_json({"type": "text", "content": "remember I park on level 3"})
            turn = _drain_until_turn_end(ws)
            assert any(m.get("type") == "tool_event" and m.get("name") == "remember" for m in turn)

    # Verify persistence with an independent connection.
    async def _check() -> tuple[int, list[str], int]:
        conn = await asyncpg.connect(TEST_DATABASE_URL)
        try:
            msg_count = await conn.fetchval(
                "SELECT count(*) FROM messages WHERE user_id = $1", user_id
            )
            roles = [
                r["role"]
                for r in await conn.fetch(
                    "SELECT role FROM messages WHERE user_id = $1 ORDER BY id", user_id
                )
            ]
            actions = await conn.fetchval(
                "SELECT count(*) FROM action_log WHERE user_id = $1 AND tool = 'remember'",
                user_id,
            )
            return msg_count, roles, actions
        finally:
            await conn.close()

    msg_count, roles, action_count = asyncio.run(_check())
    assert "user" in roles  # the user's turn was stored
    assert "edith" in roles  # EDITH's reply was stored
    assert msg_count >= 2
    assert action_count == 1  # the remember action was logged
