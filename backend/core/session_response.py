"""Safe login response helpers.

Production is same-origin and authenticates with an HttpOnly cookie.  Do not
also expose the bearer token to page JavaScript unless an operator explicitly
enables the split-origin fallback.
"""
import os


def expose_bearer_token() -> bool:
    environment = os.environ.get("ENV", os.environ.get("APP_ENV", "development")).strip().lower()
    explicit = os.environ.get("ALLOW_BEARER_FALLBACK", "").strip().lower() in {
        "1", "true", "yes",
    }
    return environment not in {"production", "prod"} or explicit


def login_response(user: dict, token: str) -> dict:
    payload = {"user": user}
    if expose_bearer_token():
        payload["session_token"] = token
    return payload
