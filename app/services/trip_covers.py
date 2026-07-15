"""Resolve and proxy trip cover images from Wikipedia or fallbacks."""

from __future__ import annotations

from urllib.parse import quote

import httpx
from fastapi import HTTPException
from fastapi.responses import Response

from app.services.place_photos import HEADERS, fetch_place_photo

_cover_url_cache: dict[str, str] = {}
_cover_bytes_cache: dict[str, tuple[bytes, str]] = {}
MAX_BYTES_CACHE = 64


def _cache_key(location: str, code: str) -> str:
    return f"{location.strip().lower()}|{code.strip().lower()}"


def _search_terms(location: str) -> list[str]:
    loc = (location or "").strip()
    if not loc:
        return ["travel destination"]
    terms = [loc]
    if "," in loc:
        city = loc.split(",", 1)[0].strip()
        if city and city.lower() not in {t.lower() for t in terms}:
            terms.append(city)
    return terms


async def _resolve_cover_url(location: str, code: str) -> str:
    key = _cache_key(location, code)
    if key in _cover_url_cache:
        return _cover_url_cache[key]

    for term in _search_terms(location):
        photo = await fetch_place_photo(title=term, location=term)
        if photo:
            _cover_url_cache[key] = photo
            return photo

    seed = quote(code or location or "trip", safe="")
    fallback = f"https://picsum.photos/seed/{seed}/600/400"
    _cover_url_cache[key] = fallback
    return fallback


async def fetch_trip_cover(location: str, code: str) -> tuple[bytes, str]:
    key = _cache_key(location, code)
    if key in _cover_bytes_cache:
        return _cover_bytes_cache[key]

    url = await _resolve_cover_url(location, code)
    async with httpx.AsyncClient(timeout=12.0, headers=HEADERS, follow_redirects=True) as client:
        response = await client.get(url)
        if response.status_code != 200 or not response.content:
            seed = quote(code or location or "trip", safe="")
            response = await client.get(f"https://picsum.photos/seed/{seed}/600/400")
            if response.status_code != 200 or not response.content:
                raise HTTPException(status_code=404, detail="Cover image unavailable")

    media_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
    payload = (response.content, media_type)
    if len(_cover_bytes_cache) >= MAX_BYTES_CACHE:
        _cover_bytes_cache.pop(next(iter(_cover_bytes_cache)))
    _cover_bytes_cache[key] = payload
    return payload


async def trip_cover_response(location: str = "", code: str = "") -> Response:
    content, media_type = await fetch_trip_cover(location, code)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
