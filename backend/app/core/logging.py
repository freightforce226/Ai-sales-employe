"""
Purpose of this file.
Configures structured JSON logging for the service.
Responsibility of this file.
Ensuring consistent log format across all modules, and explicitly redacting sensitive fields before logging.
"""

import logging
import sys

import structlog

from app.core.config import get_settings

from contextvars import ContextVar

_REDACTED_KEYS = {"access_token", "refresh_token", "encrypted_access_token", "encrypted_refresh_token", "client_secret", "api_key"}
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def _redact_sensitive(_, __, event_dict: dict) -> dict:
    for key in list(event_dict.keys()):
        if key.lower() in _REDACTED_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def _inject_request_id(_, __, event_dict: dict) -> dict:
    req_id = request_id_var.get()
    if req_id:
        if "event" in event_dict and isinstance(event_dict["event"], str):
            event_dict["event"] = f"[REQ-{req_id}] {event_dict['event']}"
    return event_dict


def configure_logging() -> None:
    settings = get_settings()

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _inject_request_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_sensitive,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.dialects").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.orm").setLevel(logging.WARNING)


def get_logger(name: str):
    return structlog.get_logger(name)
