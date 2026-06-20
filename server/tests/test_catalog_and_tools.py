"""ToolCatalog builds specs over the registry; foundational tools round-trip."""

from __future__ import annotations

import asyncio

import app.agent.tools.foundational  # noqa: F401 — self-registers FoundationalConnector
import app.connectors.examples as examples
from app.agent.catalog import ToolCatalog
from app.agent.memory import Memory
from app.connectors import registry

registry.discover(examples)


def _catalog(memory: Memory | None = None, user_id: str = "u_cat") -> ToolCatalog:
    return ToolCatalog(
        registry,
        user_id=user_id,
        cred_lookup=lambda _key: None,
        extra={"memory": memory} if memory else {},
    )


def test_specs_include_foundational_and_example_echo() -> None:
    names = {spec.name for spec in _catalog().specs()}
    # Foundational tools.
    assert {"current_time", "web_lookup", "remember", "recall"} <= names
    # Example echo connector's tools.
    assert {"echo", "self_destruct"} <= names


def test_specs_carry_json_schema_parameters() -> None:
    spec = next(s for s in _catalog().specs() if s.name == "remember")
    assert spec.parameters["type"] == "object"
    assert "text" in spec.parameters["properties"]


def test_lookup_returns_live_tool() -> None:
    tool = _catalog().lookup("echo")
    assert tool is not None
    assert tool.name == "echo"
    assert asyncio.run(tool.handler(text="hi")) == {"echo": "hi"}


def test_lookup_unknown_returns_none() -> None:
    assert _catalog().lookup("does_not_exist") is None


def test_foundational_remember_recall_roundtrip() -> None:
    mem = Memory()
    catalog = _catalog(memory=mem, user_id="u_round")

    remember = catalog.lookup("remember")
    recall = catalog.lookup("recall")
    assert remember is not None and recall is not None

    asyncio.run(remember.handler(text="my dog is named Rex"))
    result = asyncio.run(recall.handler(query="dog"))
    assert result == {"memories": ["my dog is named Rex"]}


def test_per_user_memory_isolation() -> None:
    mem = Memory()
    asyncio.run(mem.remember("user_a", "secret A"))
    # A different user recalls nothing of user_a's.
    assert asyncio.run(mem.recall("user_b", "secret")) == []


def test_current_time_returns_iso() -> None:
    tool = _catalog().lookup("current_time")
    assert tool is not None
    result = asyncio.run(tool.handler())
    assert "now" in result
    # ISO-8601 with timezone offset.
    assert "T" in result["now"]


def test_web_lookup_is_stubbed_no_network() -> None:
    tool = _catalog().lookup("web_lookup")
    assert tool is not None
    result = asyncio.run(tool.handler(query="capital of malaysia"))
    assert result["stub"] is True
