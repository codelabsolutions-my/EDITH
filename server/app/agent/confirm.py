"""The confirmation gate — server-enforced, model-independent.

A ``CONFIRM`` tool (send, delete, pay, unlock...) never runs without an explicit
``ok:true`` from the user. This is enforced here, not in the prompt, so an
unreliable LLM cannot bypass it. ``await_reply`` races the user's confirmation
against the per-turn ``cancel`` event (barge-in), so an interrupt cancels a
pending confirmation instead of leaving it dangling.
"""

from __future__ import annotations

import asyncio

from ..voice.transport import Transport


class TurnCancelled(Exception):
    """Raised when the current turn is cancelled (barge-in) mid-flight."""


class ConfirmGate:
    """Gates ``CONFIRM`` tools on an explicit user reply, cancellable by barge-in."""

    async def await_reply(
        self,
        action_id: str,
        summary: str,
        transport: Transport,
        cancel: asyncio.Event,
    ) -> bool:
        """Return the user's confirmation, or raise :class:`TurnCancelled`.

        Races ``transport.request_confirm`` against ``cancel``; if the turn is
        cancelled first, the confirmation task is cancelled and we raise.
        """
        reply_task = asyncio.ensure_future(transport.request_confirm(action_id, summary))
        cancel_task = asyncio.ensure_future(cancel.wait())
        try:
            done, _ = await asyncio.wait(
                {reply_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if cancel_task in done and reply_task not in done:
                raise TurnCancelled
            return reply_task.result()
        finally:
            for task in (reply_task, cancel_task):
                if not task.done():
                    task.cancel()
