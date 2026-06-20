"""Built-in agent tools, exposed as ordinary connectors.

Foundational tools (``remember``/``recall``/``current_time``/``web_lookup``) are a
single built-in :class:`~app.agent.tools.foundational.FoundationalConnector`
registered into the *existing* connector registry, so the agent has exactly one
tool code path — no second registry.
"""

from __future__ import annotations
