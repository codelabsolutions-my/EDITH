"""End-to-end WebSocket integration over /ws using FastAPI's TestClient.

Drives the full M0 flow: auth -> remember -> gated self_destruct -> current_time.
TestClient's websocket support is synchronous, so no async harness is needed.
"""

from __future__ import annotations

from typing import Any

from app.auth.tokens import mint_access_token
from app.config import get_settings
from app.main import create_app
from fastapi.testclient import TestClient

# A stable test user id (a UUID string, as real auth would issue).
TEST_USER_ID = "11111111-1111-1111-1111-111111111111"


def _token(user_id: str = TEST_USER_ID, display_name: str = "Test User") -> str:
    settings = get_settings()
    return mint_access_token(
        user_id=user_id,
        display_name=display_name,
        secret=settings.JWT_SECRET,
        ttl_seconds=settings.JWT_ACCESS_TTL_SECONDS,
    )


def _collect_until_turn_end(ws: Any) -> list[dict[str, Any]]:
    """Read messages until a turn_end, returning all messages in the turn."""
    out: list[dict[str, Any]] = []
    while True:
        msg = ws.receive_json()
        out.append(msg)
        if msg.get("type") == "turn_end":
            return out


def _types(messages: list[dict[str, Any]]) -> list[str]:
    return [m["type"] for m in messages]


def _tool_states(messages: list[dict[str, Any]], name: str) -> list[str]:
    return [m["state"] for m in messages if m.get("type") == "tool_event" and m.get("name") == name]


def test_full_text_mode_flow() -> None:
    app = create_app()
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        # ── auth ──
        ws.send_json({"type": "auth", "token": _token()})
        auth_ok = ws.receive_json()
        assert auth_ok["type"] == "auth_ok"
        assert auth_ok["user"]["id"] == TEST_USER_ID

        # ── remember (AUTO) ──
        ws.send_json({"type": "text", "content": "remember I park on level 3"})
        turn = _collect_until_turn_end(ws)
        assert _tool_states(turn, "remember") == ["running", "done"]
        # A transcript of EDITH's reply is present.
        assert any(m.get("type") == "transcript" and m.get("role") == "edith" for m in turn)

        # ── self_destruct (CONFIRM) ──
        ws.send_json({"type": "text", "content": "run self destruct"})
        # Read up to and including the confirm_request.
        confirm_req = None
        while confirm_req is None:
            msg = ws.receive_json()
            if msg.get("type") == "confirm_request":
                confirm_req = msg
        action_id = confirm_req["action_id"]

        ws.send_json({"type": "confirm", "action_id": action_id, "ok": True})
        rest = _collect_until_turn_end(ws)
        assert "done" in _tool_states(rest, "self_destruct")

        # ── current_time (AUTO) ──
        ws.send_json({"type": "text", "content": "what time is it"})
        turn = _collect_until_turn_end(ws)
        assert _tool_states(turn, "current_time") == ["running", "done"]


def test_auth_required_first() -> None:
    app = create_app()
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        # Sending a non-auth frame first is rejected.
        ws.send_json({"type": "text", "content": "hello"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "auth_required"


def test_empty_token_rejected() -> None:
    app = create_app()
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": ""})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "auth_failed"


def test_barge_in_cancels_turn_and_session_survives() -> None:
    """A barge_in mid-turn yields status=listening (no turn_end); next turn works."""
    app = create_app()
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": _token()})
        assert ws.receive_json()["type"] == "auth_ok"

        # Start a turn, then immediately interrupt it.
        ws.send_json({"type": "text", "content": "what time is it"})
        ws.send_json({"type": "barge_in"})

        # The barge-in surfaces as status=listening (a cancelled turn sends no
        # turn_end). Read until we observe it.
        saw_listening = False
        for _ in range(20):
            msg = ws.receive_json()
            if msg.get("type") == "status" and msg.get("state") == "listening":
                saw_listening = True
                break
        assert saw_listening

        # The session survives the barge-in: a fresh turn completes normally.
        ws.send_json({"type": "text", "content": "echo hello there"})
        completed = False
        for _ in range(20):
            msg = ws.receive_json()
            if msg.get("type") == "turn_end":
                completed = True
                break
        assert completed
