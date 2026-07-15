"""Serve curated, location-appropriate trip cover images."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import Response

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
DESTINATIONS_DIR = STATIC_DIR / "destinations"
DEFAULT_COVER_PATH = DESTINATIONS_DIR / "default.svg"
FALLBACK_COVER_PATH = DESTINATIONS_DIR / "travel.jpg"

_cover_bytes_cache: dict[str, tuple[bytes, str]] = {}
MAX_BYTES_CACHE = 64

# Verified stock photos bundled in /static/destinations/
REGION_STOCK_FILES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"london|uk|england|scotland|wales|britain", re.I), "uk.jpg"),
    (re.compile(r"paris|france|lyon|nice|marseille", re.I), "france.jpg"),
    (re.compile(r"rome|milan|venice|florence|italy|naples|tuscany|sicily", re.I), "italy.jpg"),
    (re.compile(r"barcelona|madrid|spain|seville|valencia", re.I), "spain.jpg"),
    (re.compile(r"lisbon|porto|portugal", re.I), "portugal.jpg"),
    (re.compile(r"tokyo|kyoto|osaka|japan", re.I), "japan.jpg"),
    (re.compile(r"new york|nyc|san francisco|los angeles|chicago|usa|united states", re.I), "usa.jpg"),
    (re.compile(r"athens|santorini|greece", re.I), "greece.jpg"),
]


def _cache_key(location: str, code: str) -> str:
    return f"{location.strip().lower()}|{code.strip().lower()}"


def _stock_filename(location: str, name: str = "") -> str:
    loc = (location or "").strip()
    hints = f"{loc} {name}".strip()
    for pattern, filename in REGION_STOCK_FILES:
        if pattern.search(hints):
            return filename
    return "travel.jpg"


def _read_cover_file(path: Path) -> tuple[bytes, str] | None:
    if not path.is_file():
        return None
    suffix = path.suffix.lower()
    media_type = "image/svg+xml" if suffix == ".svg" else "image/jpeg"
    return path.read_bytes(), media_type


async def fetch_trip_cover(location: str, code: str, name: str = "") -> tuple[bytes, str]:
    key = _cache_key(location or name, code)
    if key in _cover_bytes_cache:
        return _cover_bytes_cache[key]

    filename = _stock_filename(location, name)
    payload = _read_cover_file(DESTINATIONS_DIR / filename)
    if not payload:
        payload = _read_cover_file(FALLBACK_COVER_PATH)
    if not payload:
        payload = _read_cover_file(DEFAULT_COVER_PATH)
    if not payload:
        raise HTTPException(status_code=404, detail="Cover image unavailable")

    if len(_cover_bytes_cache) >= MAX_BYTES_CACHE:
        _cover_bytes_cache.pop(next(iter(_cover_bytes_cache)))
    _cover_bytes_cache[key] = payload
    return payload


async def trip_cover_response(location: str = "", code: str = "", name: str = "") -> Response:
    content, media_type = await fetch_trip_cover(location, code, name)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
