"""Shared security helpers: secrets, CSRF, rate limiting."""

from __future__ import annotations

import os
import secrets
import time
from collections import defaultdict

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

CSRF_COOKIE = "gdp_csrf"
CSRF_HEADER = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_MAX_AGE = 60 * 60 * 24

_DEV_SECRET = "gdp-dev-secret-change-in-production"
_secret_key: str | None = None
_serializer: URLSafeTimedSerializer | None = None

_rate_buckets: dict[str, list[float]] = defaultdict(list)


def is_production() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "").lower()
    if env in {"production", "prod"}:
        return True
    return bool(os.getenv("RENDER"))


def get_secret_key() -> str:
    global _secret_key, _serializer
    if _secret_key is not None:
        return _secret_key

    key = (os.getenv("SECRET_KEY") or "").strip()
    if not key:
        if is_production():
            raise RuntimeError(
                "SECRET_KEY must be set in production. "
                "On Render: open your service → Environment → add SECRET_KEY "
                "(generate a random string, e.g. python -c \"import secrets; print(secrets.token_urlsafe(32))\")."
            )
        key = _DEV_SECRET

    _secret_key = key
    _serializer = URLSafeTimedSerializer(key, salt="gdp-security")
    return key


def _get_serializer() -> URLSafeTimedSerializer:
    get_secret_key()
    assert _serializer is not None
    return _serializer


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def rate_limit(key: str, *, max_calls: int, window_sec: int) -> bool:
    """Return True if the request is allowed."""
    now = time.time()
    bucket = _rate_buckets[key]
    bucket[:] = [stamp for stamp in bucket if now - stamp < window_sec]
    if len(bucket) >= max_calls:
        return False
    bucket.append(now)
    return True


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_csrf_cookie(request: Request) -> str | None:
    token = request.cookies.get(CSRF_COOKIE)
    if token and len(token) >= 16:
        return None
    return new_csrf_token()


def validate_csrf(request: Request) -> bool:
    cookie_token = request.cookies.get(CSRF_COOKIE)
    if not cookie_token:
        return False

    header_token = request.headers.get(CSRF_HEADER)
    if header_token and secrets.compare_digest(header_token, cookie_token):
        return True

    return False


def read_session_token(token: str, *, max_age: int) -> str | None:
    try:
        data = _get_serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid")
    return uid if isinstance(uid, str) and uid else None


def create_session_token(user_id: str) -> str:
    return _get_serializer().dumps({"uid": user_id})
