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

_REDACTED_KEYS = {"access_token", "refresh_token", "encrypted_access_token", "encrypted_refresh_token", "client_secret", "api_key", "password", "secret", "cookie", "jwt", "private_key", "certificate"}
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

def recursive_sanitize(val, key_name="", depth=0):
    if depth > 5:
        return "<truncated: depth exceeded>"
        
    key_lower = str(key_name).lower()
    
    if isinstance(val, str):
        val_len = len(val)
        
        # 1. Traceback
        if "traceback" in key_lower or "stack" in key_lower or "Traceback (most recent call last):" in val:
            lines = val.splitlines()
            if len(lines) > 40:
                return "\n".join(lines[:40]) + f"\n<traceback truncated | {len(lines)} lines>"
            return val
            
        # 2. Base64
        if any(p in key_lower for p in ("contentbytes", "base64", "token_bytes")):
            return f"<Base64 omitted | {val_len} chars>"
            
        # 3. Token / Secret / Password
        if any(p in key_lower for p in ("token", "password", "secret", "cookie", "jwt", "authorization", "oauth")):
            return "<Token hidden>"
            
        # 4. HTML / MIME
        if any(p in key_lower for p in ("html", "mime")) or val.strip().startswith("<html") or val.strip().startswith("<!doctype html"):
            return f"<HTML omitted | {val_len} chars>"
            
        # 5. Email body / content / payload
        if any(p in key_lower for p in ("body", "payload", "message", "raw_message", "smtp_body", "graph_payload", "request_body", "response_body")):
            return f"<Content omitted | {val_len} chars>"
            
        # Truncate normal strings larger than 200 chars
        if val_len > 200:
            return val[:200] + f" <truncated | {val_len} chars>"
            
        return val

    elif isinstance(val, bytes):
        return f"<Binary omitted | {len(val)} bytes>"

    elif isinstance(val, dict):
        if len(val) > 20:
            return {"<truncated>": "collection size exceeded"}
        return {str(k): recursive_sanitize(v, str(k), depth + 1) for k, v in val.items()}

    elif isinstance(val, (list, tuple, set)):
        if len(val) > 20:
            val = list(val)[:20]
        sanitized_list = [recursive_sanitize(item, key_name, depth + 1) for item in val]
        if isinstance(val, tuple):
            return tuple(sanitized_list)
        if isinstance(val, set):
            return set(sanitized_list)
        return sanitized_list

    elif hasattr(val, "__dict__"):
        try:
            obj_dict = val.__dict__
            return {"__class__": val.__class__.__name__, **{k: recursive_sanitize(v, k, depth + 1) for k, v in obj_dict.items() if not k.startswith("_")}}
        except Exception:
            return f"<Object {val.__class__.__name__} omitted>"

    return val

def _recursive_sanitize_processor(_, __, event_dict: dict) -> dict:
    for key in list(event_dict.keys()):
        event_dict[key] = recursive_sanitize(event_dict[key], key)
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
            _recursive_sanitize_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set third-party loggers to WARNING or ERROR to suppress noise
    loggers_to_mute = [
        "httpcore", "httpx", "sqlalchemy", "sqlalchemy.engine", 
        "sqlalchemy.pool", "sqlalchemy.dialects", "sqlalchemy.orm",
        "asyncio", "concurrent", "imaplib", "smtplib", "email", "mail",
        "urllib3", "aiohttp", "msal", "azure", "multipart", "h11", 
        "charset_normalizer", "uvicorn.access"
    ]
    for logger_name in loggers_to_mute:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
        
    for logger_name in list(logging.root.manager.loggerDict.keys()):
        if not logger_name.startswith("app") and not logger_name.startswith("uvicorn"):
            logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str):
    return structlog.get_logger(name)
