"""HTTP middleware for CSRF protection."""

from __future__ import annotations

import secrets
from urllib.parse import parse_qs

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.dependencies import apply_pending_member_cookie
from app.services.security import CSRF_COOKIE, CSRF_FORM_FIELD, CSRF_HEADER, ensure_csrf_cookie, validate_csrf


def _csrf_from_urlencoded(body: bytes) -> str | None:
    if not body:
        return None
    parsed = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    values = parsed.get(CSRF_FORM_FIELD)
    if not values:
        return None
    token = values[0]
    return token if isinstance(token, str) and token else None


def _csrf_error_response(request: Request) -> Response:
    if "application/json" in request.headers.get("accept", "") or request.url.path.startswith("/api/"):
        return JSONResponse({"error": "Invalid or missing CSRF token"}, status_code=403)
    return Response("Invalid or missing CSRF token", status_code=403)


async def csrf_middleware(request: Request, call_next):
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        response = await call_next(request)
        apply_pending_member_cookie(request, response)
        token = ensure_csrf_cookie(request)
        if token:
            response.set_cookie(
                CSRF_COOKIE,
                token,
                max_age=60 * 60 * 24,
                httponly=False,
                samesite="lax",
                secure=request.url.scheme == "https",
            )
        return response

    content_type = request.headers.get("content-type", "")
    body = b""
    replay_body = False

    if validate_csrf(request):
        pass
    elif content_type.startswith("application/x-www-form-urlencoded"):
        body = await request.body()
        replay_body = True
        form_token = _csrf_from_urlencoded(body)
        cookie_token = request.cookies.get(CSRF_COOKIE)
        if not form_token or not cookie_token or not secrets.compare_digest(form_token, cookie_token):
            return _csrf_error_response(request)
    else:
        header_token = request.headers.get(CSRF_HEADER)
        cookie_token = request.cookies.get(CSRF_COOKIE)
        if not header_token or not cookie_token or not secrets.compare_digest(header_token, cookie_token):
            return _csrf_error_response(request)

    if replay_body:
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive)

    response = await call_next(request)
    apply_pending_member_cookie(request, response)

    token = ensure_csrf_cookie(request)
    if token:
        response.set_cookie(
            CSRF_COOKIE,
            token,
            max_age=60 * 60 * 24,
            httponly=False,
            samesite="lax",
            secure=request.url.scheme == "https",
        )

    return response
