"""Validation for user-supplied links rendered by the ERP frontend."""
from urllib.parse import urlsplit


def external_http_url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("URL must be a string")
    value = value.strip()
    if not value or len(value) > 2048 or any(ord(char) < 32 for char in value):
        raise ValueError("Invalid URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must not contain credentials")
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("Invalid URL port")
    return value
