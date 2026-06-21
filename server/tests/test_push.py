"""Push senders: LogPushSender + FcmPushSender (mocked transport)."""

from __future__ import annotations

import asyncio

import httpx
from app.proactivity.push import (
    DeviceTarget,
    FcmPushSender,
    LogPushSender,
    Notification,
)


def test_log_sender_counts_targets() -> None:
    targets = [DeviceTarget("fcm", "a"), DeviceTarget("web", "b")]
    n = asyncio.run(LogPushSender().send(targets, Notification("Hi", "there")))
    assert n == 2


def test_fcm_sender_posts_and_counts_delivered() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer fcm-access"
        import json

        seen.append(json.loads(request.content)["message"])
        return httpx.Response(200, json={"name": "ok"})

    async def token_provider() -> str:
        return "fcm-access"

    sender = FcmPushSender("proj-1", token_provider, transport=httpx.MockTransport(handler))
    targets = [
        DeviceTarget("fcm", "tok-1"),
        DeviceTarget("apns", "skip"),
        DeviceTarget("fcm", "tok-2"),
    ]
    delivered = asyncio.run(sender.send(targets, Notification("Reminder", "Call Ali")))

    assert delivered == 2  # only the two fcm targets
    assert {m["token"] for m in seen} == {"tok-1", "tok-2"}
    assert seen[0]["notification"] == {"title": "Reminder", "body": "Call Ali"}


def test_fcm_sender_no_fcm_targets_is_noop() -> None:
    async def token_provider() -> str:  # pragma: no cover - must not be called
        raise AssertionError("should not mint a token with no fcm targets")

    sender = FcmPushSender("proj-1", token_provider)
    n = asyncio.run(sender.send([DeviceTarget("web", "x")], Notification("a", "b")))
    assert n == 0
