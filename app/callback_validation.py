"""Валидация callback_url (SSRF-защита). Общая для API и воркера."""

import os
from urllib.parse import urlparse


def _allowed_hosts() -> set[str]:
    return {h.strip() for h in os.getenv("CALLBACK_ALLOWED_HOSTS", "").split(",") if h.strip()}


def validate_callback_url(callback_url: str) -> None:
    """Бросает ValueError, если URL не http(s) или хост не в белом списке."""
    parsed = urlparse(callback_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"callback scheme '{parsed.scheme}' not allowed")
    host = parsed.hostname
    if host not in _allowed_hosts():
        raise ValueError(f"callback host '{host}' not allowed")
