"""Structured logging (structlog) with a per-session/request correlation id.

JSON in production, a readable console renderer in development. A ``contextvar``
holds the correlation id so every log line within a WS session or request can be
traced. Discipline (engineering.md): never log tokens, PII, audio, or message
contents — log identifiers (``user_id``, ``conversation_id``), not contents.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import cast

import structlog
from structlog.types import EventDict, WrappedLogger

# Correlation id for the current WS session / HTTP request (empty when unset).
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def _add_correlation_id(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    cid = correlation_id.get()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def configure_logging(*, level: str = "info", json: bool = True) -> None:
    """Configure structlog + stdlib logging once at startup.

    ``json=True`` renders one JSON object per line (production); ``False`` uses a
    readable console renderer (development).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", level=log_level)

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_correlation_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
