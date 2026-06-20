"""Connector conformance suite.

Every registered connector must satisfy the contract in
``app.connectors.base``. Contributors run this with ``make test-connectors``.
"""

from __future__ import annotations

import asyncio

import app.connectors.examples as examples
from app.connectors import ConnectorContext, registry, validate_connector

# Import all example connectors so they self-register.
registry.discover(examples)


def _ctx() -> ConnectorContext:
    return ConnectorContext(user_id="conformance-test")


def test_some_connectors_registered() -> None:
    assert registry.all(), "expected at least one registered connector"


def test_all_registered_connectors_are_valid() -> None:
    for connector in registry.all():
        validate_connector(connector)  # raises ConnectorError on any violation


def test_example_echo_contract() -> None:
    echo = registry.get("example_echo")
    assert echo is not None, "example_echo connector should be registered"

    tools = {t.name: t for t in echo.tools(_ctx())}
    assert set(tools) == {"echo", "self_destruct"}

    # The reversible tool is AUTO; the irreversible one must be CONFIRM.
    assert tools["echo"].tool_class.value == "auto"
    assert tools["self_destruct"].tool_class.value == "confirm"


def test_example_echo_handler_runs() -> None:
    echo = registry.get("example_echo")
    assert echo is not None
    echo_tool = next(t for t in echo.tools(_ctx()) if t.name == "echo")
    result = asyncio.run(echo_tool.handler(text="hello"))
    assert result == {"echo": "hello"}
