"""IlmuLLM streaming + tool-call reassembly — driven offline via a mock transport.

No network: an ``httpx.MockTransport`` feeds a scripted SSE body so the full
streaming path (text deltas, fragmented tool calls, finish reason) is deterministic.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from app.agent.llm import TextDelta, ToolCallDelta, TurnEnd
from app.agent.llm_ilmu import (
    IlmuLLM,
    _accumulate_tool_call,
    _finalise_tool_calls,
    _sse_data,
)
from app.config import Settings


def _chunk(delta: dict, finish: str | None = None) -> dict:
    return {"choices": [{"delta": delta, "finish_reason": finish}]}


# A scripted SSE stream: text, a tool call fragmented across two chunks, then done.
_SSE_BODY = (
    "".join(
        f"data: {json.dumps(obj)}\n\n"
        for obj in [
            _chunk({"content": "Hi "}),
            _chunk(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_x",
                            "function": {"name": "current_time", "arguments": ""},
                        }
                    ]
                }
            ),
            _chunk({"tool_calls": [{"index": 0, "function": {"arguments": "{}"}}]}),
            _chunk({}, finish="tool_calls"),
        ]
    )
    + "data: [DONE]\n\n"
).encode()


class _FakeCancel:
    @staticmethod
    def is_set() -> bool:
        return False


def _settings() -> Settings:
    return Settings(ILMU_API_BASE="https://api.test/v1", ILMU_API_KEY="sk-test")


def test_stream_reassembles_text_and_tool_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["authorization"] == "Bearer sk-test"
        return httpx.Response(200, content=_SSE_BODY)

    llm = IlmuLLM(_settings(), transport=httpx.MockTransport(handler))

    async def collect() -> list:
        msgs = [{"role": "user", "content": "hi"}]
        out = []
        async for delta in llm.stream(msgs, [], cancel=_FakeCancel()):
            out.append(delta)
        return out

    deltas = asyncio.run(collect())

    texts = [d.text for d in deltas if isinstance(d, TextDelta)]
    assert "".join(texts) == "Hi "
    calls = [d.call for d in deltas if isinstance(d, ToolCallDelta)]
    assert len(calls) == 1
    assert calls[0].name == "current_time"
    assert calls[0].arguments == {}
    assert calls[0].id == "call_x"
    ends = [d for d in deltas if isinstance(d, TurnEnd)]
    assert ends and ends[-1].finish_reason == "tool_calls"


def test_stream_aborts_on_cancel() -> None:
    class _Cancelled:
        @staticmethod
        def is_set() -> bool:
            return True

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_SSE_BODY)

    llm = IlmuLLM(_settings(), transport=httpx.MockTransport(handler))

    async def collect() -> list:
        return [
            d
            async for d in llm.stream([{"role": "user", "content": "hi"}], [], cancel=_Cancelled())
        ]

    deltas = asyncio.run(collect())
    # Cancelled before consuming any chunk → no tool calls, a cancelled TurnEnd.
    assert all(not isinstance(d, ToolCallDelta) for d in deltas)
    assert isinstance(deltas[-1], TurnEnd)
    assert deltas[-1].finish_reason == "cancelled"


def test_requires_credentials() -> None:
    with pytest.raises(ValueError):
        IlmuLLM(Settings(ILMU_API_BASE="", ILMU_API_KEY=""))


def test_sse_data_parsing() -> None:
    assert _sse_data("data: {}") == "{}"
    assert _sse_data("data:[DONE]") == "[DONE]"
    assert _sse_data(": comment") is None
    assert _sse_data("") is None


def test_tool_call_fragments_accumulate_by_index() -> None:
    partial: dict[int, dict] = {}
    _accumulate_tool_call(partial, {"index": 0, "id": "c1", "function": {"name": "echo"}})
    _accumulate_tool_call(partial, {"index": 0, "function": {"arguments": '{"text":'}})
    _accumulate_tool_call(partial, {"index": 0, "function": {"arguments": '"hi"}'}})
    calls = _finalise_tool_calls(partial)
    assert len(calls) == 1
    assert calls[0].name == "echo"
    assert calls[0].arguments == {"text": "hi"}


def test_finalise_skips_nameless_and_tolerates_bad_json() -> None:
    partial = {
        0: {"id": "a", "name": None, "arguments": ""},  # no name -> skipped
        1: {"id": "b", "name": "t", "arguments": "{not json"},  # bad args -> {}
    }
    calls = _finalise_tool_calls(partial)
    assert len(calls) == 1
    assert calls[0].name == "t"
    assert calls[0].arguments == {}
