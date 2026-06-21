"""Push notification delivery seam.

The scheduler delivers nudges through a :class:`PushSender`. Two implementations:

- :class:`LogPushSender` — the dev/default: structured-logs the notification so the
  whole proactivity loop is exercisable with no external service.
- :class:`FcmPushSender` — Firebase Cloud Messaging HTTP v1. It needs a project id and
  an OAuth access token (minted from a service account — wired when FCM creds exist);
  the HTTP call is injectable for tests.

APNs (iOS direct) follows the same seam later. Web push too.
"""

from __future__ import annotations

import abc
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger("edith.push")

_REQUEST_TIMEOUT = httpx.Timeout(15.0, connect=10.0)


@dataclass(frozen=True)
class Notification:
    """A push notification payload."""

    title: str
    body: str
    data: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DeviceTarget:
    """A registered push target."""

    platform: str  # fcm | apns | web
    token: str


class PushSender(abc.ABC):
    """Delivers a notification to a user's devices. Returns the count delivered."""

    @abc.abstractmethod
    async def send(self, targets: list[DeviceTarget], notification: Notification) -> int:
        raise NotImplementedError


class LogPushSender(PushSender):
    """Dev sender: logs instead of delivering (no external dependency)."""

    async def send(self, targets: list[DeviceTarget], notification: Notification) -> int:
        for t in targets:
            log.info(
                "push (logged, not delivered)",
                extra={"platform": t.platform, "title": notification.title},
            )
        return len(targets)


# A coroutine returning a valid FCM OAuth access token (minted from a service account).
AccessTokenProvider = Callable[[], Awaitable[str]]


class FcmPushSender(PushSender):
    """Firebase Cloud Messaging (HTTP v1) sender."""

    def __init__(
        self,
        project_id: str,
        token_provider: AccessTokenProvider,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        self._token_provider = token_provider
        self._transport = transport

    async def send(self, targets: list[DeviceTarget], notification: Notification) -> int:
        fcm_targets = [t for t in targets if t.platform == "fcm"]
        if not fcm_targets:
            return 0
        access_token = await self._token_provider()
        headers = {"Authorization": f"Bearer {access_token}"}
        delivered = 0
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, transport=self._transport) as client:
            for t in fcm_targets:
                payload = _fcm_message(t.token, notification)
                resp = await client.post(self._url, json=payload, headers=headers)
                if resp.status_code == 200:
                    delivered += 1
                else:
                    log.warning("fcm send failed", extra={"status": resp.status_code})
        return delivered


def _fcm_message(token: str, notification: Notification) -> dict[str, Any]:
    return {
        "message": {
            "token": token,
            "notification": {"title": notification.title, "body": notification.body},
            "data": notification.data,
        }
    }
