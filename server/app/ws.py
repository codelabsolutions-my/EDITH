"""The WebSocket hub — auth handshake, then run a :class:`Session`.

Protocol (M0):
- First client frame must be ``{"type":"auth","token":"<token>"}``.
- Server replies ``{"type":"auth_ok","user":{...}}`` on success.
- Thereafter, text-mode turns flow per ``docs/specs/phase-1-runtime.md``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .auth import AuthError, verify_jwt
from .connectors.registry import ConnectorRegistry, registry
from .session import Session, WsMessage

log = logging.getLogger("edith.ws")

router = APIRouter()


async def _auth_handshake(ws: WebSocket) -> Any | None:
    """Run the first-frame auth handshake. Returns the user, or None to close."""
    try:
        first = await ws.receive_json()
    except Exception:
        await ws.send_json({"type": "error", "code": "auth_required", "message": "auth first"})
        return None

    if not isinstance(first, dict) or first.get("type") != "auth":
        await ws.send_json({"type": "error", "code": "auth_required", "message": "auth first"})
        return None

    try:
        user = verify_jwt(str(first.get("token", "")))
    except AuthError as exc:
        await ws.send_json({"type": "error", "code": "auth_failed", "message": str(exc)})
        return None

    await ws.send_json(
        {"type": "auth_ok", "user": {"id": user.id, "display_name": user.display_name}}
    )
    return user


def _make_endpoint(reg: ConnectorRegistry) -> Any:
    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        user = await _auth_handshake(websocket)
        if user is None:
            await websocket.close(code=4401)
            return

        log.info("ws session started", extra={"user_id": user.id})

        async def ws_receive() -> WsMessage:
            # Returns the next frame as JSON or bytes; raises on disconnect.
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            if (data := message.get("bytes")) is not None:
                return WsMessage(bytes=data)
            text = message.get("text")
            if text is not None:
                import json

                return WsMessage(json=json.loads(text))
            return WsMessage(json={})

        session = Session(
            user_id=user.id,
            registry=reg,
            ws_send=websocket.send_json,
            ws_receive=ws_receive,
        )
        try:
            await session.run()
        except WebSocketDisconnect:
            pass
        finally:
            log.info("ws session ended", extra={"user_id": user.id})

    return ws_endpoint


# Register the default-registry endpoint at /ws (FastAPI APIRouter websocket API).
router.add_api_websocket_route("/ws", _make_endpoint(registry))
