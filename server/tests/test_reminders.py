"""Reminders connector tool + parse_remind_at + device registration route."""

from __future__ import annotations

import asyncio
from datetime import UTC

import asyncpg
import pytest
from app.connectors.base import ConnectorContext
from app.connectors.reminders import RemindersConnector
from app.main import create_app
from app.proactivity.reminders import ReminderStore, parse_remind_at
from fastapi.testclient import TestClient
from tests.conftest import TEST_DATABASE_URL, reset_db


def test_parse_remind_at_handles_naive_and_zulu() -> None:
    assert parse_remind_at("2026-06-22T09:00:00+08:00").tzinfo is not None
    assert parse_remind_at("2026-06-22T09:00:00Z").tzinfo == UTC
    assert parse_remind_at("2026-06-22T09:00:00").tzinfo == UTC  # naive -> UTC
    with pytest.raises(ValueError):
        parse_remind_at("not a time")


def test_tool_inert_without_store() -> None:
    tools = {t.name: t for t in RemindersConnector().tools(ConnectorContext(user_id="u"))}
    result = asyncio.run(tools["set_reminder"].handler(text="x", remind_at="2026-06-22T09:00:00Z"))
    assert result["ok"] is False


def test_set_and_list_reminder_via_tool(pg_dsn: str) -> None:
    async def scenario() -> None:
        pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=3)
        assert pool is not None
        try:
            await reset_db(pool)
            uid = str(
                await pool.fetchval(
                    "INSERT INTO users (primary_email) VALUES ('t@x.com') RETURNING id"
                )
            )
            store = ReminderStore(pool, uid)
            ctx = ConnectorContext(user_id=uid, extra={"reminder_store": store})
            tools = {t.name: t for t in RemindersConnector().tools(ctx)}

            set_res = await tools["set_reminder"].handler(
                text="call the dentist", remind_at="2026-06-22T09:00:00+08:00"
            )
            assert set_res["ok"] is True
            list_res = await tools["list_reminders"].handler()
            assert any(r["text"] == "call the dentist" for r in list_res["reminders"])

            # Persisted.
            count = await pool.fetchval("SELECT count(*) FROM reminders WHERE user_id=$1", uid)
            assert count == 1
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_set_reminder_rejects_bad_timestamp(pg_dsn: str) -> None:
    async def scenario() -> None:
        pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=2)
        assert pool is not None
        try:
            await reset_db(pool)
            uid = str(
                await pool.fetchval(
                    "INSERT INTO users (primary_email) VALUES ('b@x.com') RETURNING id"
                )
            )
            ctx = ConnectorContext(user_id=uid, extra={"reminder_store": ReminderStore(pool, uid)})
            tools = {t.name: t for t in RemindersConnector().tools(ctx)}
            res = await tools["set_reminder"].handler(text="x", remind_at="whenever")
            assert res["ok"] is False
        finally:
            await pool.close()

    asyncio.run(scenario())


def _dev_token(client: TestClient) -> str:
    return client.post(
        "/auth/dev-login", json={"email": "dev@x.com", "display_name": "Dev"}
    ).json()["access_token"]


def test_device_registration(pg_dsn: str) -> None:
    async def _reset() -> None:
        pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=2)
        assert pool is not None
        await reset_db(pool)
        await pool.close()

    asyncio.run(_reset())

    app = create_app()
    with TestClient(app) as client:
        token = _dev_token(client)
        ok = client.post(
            "/devices/register",
            json={"platform": "fcm", "token": "device-xyz"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json() == {"ok": True}

        # No auth → 401; bad platform → 400.
        assert (
            client.post("/devices/register", json={"platform": "fcm", "token": "z"}).status_code
            == 401
        )
        bad = client.post(
            "/devices/register",
            json={"platform": "carrier-pigeon", "token": "z"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert bad.status_code == 400

    async def _count() -> int:
        conn = await asyncpg.connect(TEST_DATABASE_URL)
        try:
            return await conn.fetchval(
                "SELECT count(*) FROM device_tokens WHERE token='device-xyz'"
            )
        finally:
            await conn.close()

    assert asyncio.run(_count()) == 1
