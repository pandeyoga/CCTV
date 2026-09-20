"""Helpers to keep secrets (RTSP credentials, API keys) out of logs."""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_BEARER_RE = re.compile(r"(Bearer\s+)\S+", re.IGNORECASE)


def redact_url(url: str) -> str:
    """rtsp://user:pass@host/path -> rtsp://***:***@host/path"""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid-url>"
    if not parts.netloc or "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, f"***:***@{host}", parts.path, parts.query, parts.fragment))


def redact_secret(value: str | None, keep: int = 0) -> str:
    if not value:
        return "<unset>"
    return "***" if keep <= 0 else f"{value[:keep]}***"


def redact_text(text: str) -> str:
    return _BEARER_RE.sub(r"\1***", text)
