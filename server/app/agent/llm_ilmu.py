"""ILMU LLM provider — streaming tool-calling over the OpenAI-compatible API.

Implements :class:`~app.agent.llm.LLMProvider` against ILMU's ``/chat/completions``
(``nemo-super`` for tools/reasoning, spike-validated). The agent loop is unchanged:
it streams :class:`TextDelta` / :class:`ToolCallDelta` / :class:`TurnEnd` exactly as
it does from the stub. Streamed tool-call fragments are reassembled by ``index``
before being surfaced as a single :class:`ToolCall`.

``ilmu-v3.1`` is intentionally **not** used here — the spike proved it unreliable at
tool-calling (see ADR 0002 / CLAUDE.md).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from ..config import Settings
from .llm import (
    LLMDelta,
    LLMProvider,
    Message,
    TextDelta,
    ToolCall,
    ToolCallDelta,
    ToolSpec,
    TurnEnd,
)

log = logging.getLogger("edith.llm.ilmu")

# Per-request ceiling. Turns are short; a real stall should fail fast, not hang.
_REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class IlmuLLM(LLMProvider):
    """Streaming provider backed by the ILMU OpenAI-compatible chat API."""

    def __init__(
        self,
        settings: Settings,
        *,
        model: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not settings.ILMU_API_BASE or not settings.ILMU_API_KEY:
            raise ValueError("IlmuLLM requires ILMU_API_BASE and ILMU_API_KEY")
        self._base = settings.ILMU_API_BASE.rstrip("/")
        self._key = settings.ILMU_API_KEY
        self._model = model or settings.ILMU_TOOL_MODEL
        # Injectable transport so the streaming path is testable without a network.
        self._transport = transport

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        *,
        cancel: Any,
    ) -> AsyncIterator[LLMDelta]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": list(messages),
            "stream": True,
            "temperature": 0.4,
        }
        if tools:
            payload["tools"] = [_tool_to_openai(t) for t in tools]
            payload["tool_choice"] = "auto"

        headers = {"Authorization": f"Bearer {self._key}"}
        # Tool-call fragments accumulate here, keyed by their stream index.
        partial: dict[int, dict[str, Any]] = {}
        finish_reason = "stop"

        async with (
            httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, transport=self._transport) as client,
            client.stream(
                "POST", f"{self._base}/chat/completions", json=payload, headers=headers
            ) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if cancel.is_set():
                    finish_reason = "cancelled"
                    break
                data = _sse_data(line)
                if data is None:
                    continue
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get("delta") or {}

                text = delta.get("content")
                if text:
                    yield TextDelta(text=text)

                for tc in delta.get("tool_calls") or []:
                    _accumulate_tool_call(partial, tc)

                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]

        for call in _finalise_tool_calls(partial):
            yield ToolCallDelta(call=call)
        yield TurnEnd(finish_reason=finish_reason)


def _tool_to_openai(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _sse_data(line: str) -> str | None:
    """Extract the payload of an SSE ``data:`` line, or None for non-data lines."""
    if not line or not line.startswith("data:"):
        return None
    return line[len("data:") :].strip()


def _accumulate_tool_call(partial: dict[int, dict[str, Any]], tc: dict[str, Any]) -> None:
    idx = tc.get("index", 0)
    slot = partial.setdefault(idx, {"id": None, "name": None, "arguments": ""})
    if tc.get("id"):
        slot["id"] = tc["id"]
    fn = tc.get("function") or {}
    if fn.get("name"):
        slot["name"] = fn["name"]
    if fn.get("arguments"):
        slot["arguments"] += fn["arguments"]


def _finalise_tool_calls(partial: dict[int, dict[str, Any]]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for idx in sorted(partial):
        slot = partial[idx]
        if not slot["name"]:
            continue
        try:
            arguments = json.loads(slot["arguments"]) if slot["arguments"] else {}
        except json.JSONDecodeError:
            log.warning("could not parse tool arguments", extra={"tool": slot["name"]})
            arguments = {}
        calls.append(
            ToolCall(
                id=slot["id"] or f"call_{idx}",
                name=slot["name"],
                arguments=arguments if isinstance(arguments, dict) else {},
            )
        )
    return calls
