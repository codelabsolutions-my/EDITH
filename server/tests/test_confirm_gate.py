"""The confirmation gate in isolation: reply pass-through and cancel race."""

from __future__ import annotations

import asyncio

from app.agent.confirm import ConfirmGate, TurnCancelled
from tests.conftest import RecordingTransport


def test_await_reply_returns_user_answer() -> None:
    transport = RecordingTransport([], confirm_answers={"a1": True})
    gate = ConfirmGate()
    cancel = asyncio.Event()

    ok = asyncio.run(gate.await_reply("a1", "send it?", transport, cancel))

    assert ok is True
    assert transport.confirm_requests == [("a1", "send it?")]


def test_await_reply_returns_false_on_decline() -> None:
    transport = RecordingTransport([], confirm_answers={"a1": False})
    gate = ConfirmGate()

    ok = asyncio.run(gate.await_reply("a1", "send it?", transport, asyncio.Event()))

    assert ok is False


def test_cancel_before_reply_raises_turn_cancelled() -> None:
    """If cancel fires and the reply never comes, await_reply raises TurnCancelled."""

    class NeverReplies(RecordingTransport):
        async def request_confirm(self, action_id: str, summary: str) -> bool:
            self.confirm_requests.append((action_id, summary))
            await asyncio.Event().wait()  # never resolves
            raise AssertionError("unreachable")

    async def scenario() -> None:
        transport = NeverReplies([])
        gate = ConfirmGate()
        cancel = asyncio.Event()
        cancel.set()  # barge-in already happened
        await gate.await_reply("a1", "send it?", transport, cancel)

    try:
        asyncio.run(scenario())
    except TurnCancelled:
        return
    raise AssertionError("expected TurnCancelled")
