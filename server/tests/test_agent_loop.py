"""Agent-loop behaviour: happy path, confirm gate, and barge-in.

Async code is driven with ``asyncio.run(...)`` (no pytest-asyncio).
"""

from __future__ import annotations

import asyncio

import app.agent.tools.foundational  # noqa: F401 — self-registers FoundationalConnector
import app.connectors.examples as examples
from app.agent.catalog import ToolCatalog
from app.agent.confirm import ConfirmGate
from app.agent.llm import StubLLM
from app.agent.loop import AgentLoop
from app.agent.memory import InMemoryMemory, Memory
from app.connectors import registry
from app.events import (
    ConfirmRequest,
    LLMToken,
    Status,
    ToolEvent,
    TurnComplete,
)
from tests.conftest import RecordingTransport

# Ensure example connectors (example_echo) are registered for the catalog.
registry.discover(examples)


def _build_loop(
    transport: RecordingTransport,
    *,
    user_id: str = "u_test",
    memory: Memory | None = None,
) -> AgentLoop:
    mem = memory or InMemoryMemory()
    catalog = ToolCatalog(
        registry,
        user_id=user_id,
        cred_lookup=lambda _key: None,
        extra={"memory": mem},
    )
    return AgentLoop(
        user_id=user_id,
        transport=transport,
        llm=StubLLM(),
        catalog=catalog,
        memory=mem,
        confirm_gate=ConfirmGate(),
    )


def _tool_events(transport: RecordingTransport, name: str) -> list[str]:
    return [e.state for e in transport.events if isinstance(e, ToolEvent) and e.name == name]


def test_auto_tool_runs_and_response_emitted() -> None:
    """A 'what time' turn runs current_time (AUTO) and emits a reply + turn_end."""
    transport = RecordingTransport(["what time is it now"])
    loop = _build_loop(transport)

    asyncio.run(loop.run())

    assert _tool_events(transport, "current_time") == ["running", "done"]
    assert any(isinstance(e, LLMToken) for e in transport.events)
    assert any(isinstance(e, TurnComplete) for e in transport.events)
    assert transport.statuses[0] is Status.THINKING
    assert transport.statuses[-1] is Status.IDLE
    # The AUTO tool was recorded in the in-memory action log.
    assert [a.tool for a in loop.action_log] == ["current_time"]


def test_confirm_tool_runs_only_on_ok_true() -> None:
    """self_destruct (CONFIRM) emits confirm_request and runs when ok=true."""
    transport = RecordingTransport(["please run self destruct now"])
    # Answer the (single) confirm request with True; action_id is call_<n>.
    transport._confirm_answers = {"call_1": True}
    loop = _build_loop(transport)

    asyncio.run(loop.run())

    assert len(transport.confirm_requests) == 1
    assert any(isinstance(e, ConfirmRequest) for e in transport.events)
    assert _tool_events(transport, "self_destruct") == ["running", "done"]
    assert [a.tool for a in loop.action_log] == ["self_destruct"]


def test_confirm_tool_skipped_on_ok_false() -> None:
    """ok=false skips the CONFIRM handler — no action logged."""
    transport = RecordingTransport(
        ["please run self destruct now"], confirm_answers={"call_1": False}
    )
    loop = _build_loop(transport)

    asyncio.run(loop.run())

    assert len(transport.confirm_requests) == 1
    # The tool was gated and declined: no action_log entry, no handler run.
    assert loop.action_log == []
    # We still emit a terminal tool_event so the UI clears the spinner.
    assert "done" in _tool_events(transport, "self_destruct")


def test_remember_then_recall_roundtrip_via_loop() -> None:
    """remember stores a fact the loop can later recall into the prompt."""
    mem = InMemoryMemory()
    transport = RecordingTransport(["remember I park on level 3"])
    loop = _build_loop(transport, memory=mem)

    asyncio.run(loop.run())

    assert _tool_events(transport, "remember") == ["running", "done"]
    stored = asyncio.run(mem.recall("u_test", "park"))
    assert stored == ["I park on level 3"]


def test_barge_in_cancels_turn() -> None:
    """Setting the barge-in signal mid-turn cancels the turn -> status LISTENING."""

    async def scenario() -> RecordingTransport:
        transport = RecordingTransport(["what time is it"])
        # Fire barge-in before the loop starts streaming so the cancel is observed.
        transport.barge_in_signal().set()
        loop = _build_loop(transport)
        await loop.run()
        return transport

    transport = asyncio.run(scenario())

    assert Status.LISTENING in transport.statuses
    # A cancelled turn does not complete.
    assert not any(isinstance(e, TurnComplete) for e in transport.events)
