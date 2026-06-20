"""System-prompt assembly: EDITH's personality + injected memory.

The agent loop recalls memories at turn start and renders them into the system
prompt here (primary injection path), so EDITH "remembers" without depending on
the model reliably calling ``recall``.
"""

from __future__ import annotations

from collections.abc import Sequence

# EDITH's personality. Warm, concise, Manglish-friendly — see product-design.md.
_PERSONA = (
    "You are EDITH, a warm and concise personal assistant for users in Malaysia. "
    "Speak naturally and may use light Manglish when it fits. Be direct and helpful, "
    "never verbose. When you take an action with a tool, briefly say what you did. "
    "For anything risky or irreversible, confirm with the user before doing it."
)


def system_prompt(memories: Sequence[str]) -> str:
    """Assemble the system prompt, injecting what EDITH remembers about the user."""
    if not memories:
        return _PERSONA
    block = "\n".join(f"- {m}" for m in memories)
    return f"{_PERSONA}\n\nWhat you remember about the user:\n{block}"
