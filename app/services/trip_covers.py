"""Resolve and proxy trip cover images from Wikipedia or location fallbacks."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import httpx
from fastapi import HTTPException
from fastapi.responses import Response

from app.services.place_photos import HEADERS, fetch_place_photo

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
DEFAULT_COVER_PATH = STATIC_DIR / "destinations" / "default.svg"

_cover_url_cache: dict[str, str] = {}
_cover_bytes_cache: dict[str, tuple[bytes, str]] = {}
MAX_BYTES_CACHE = 64

REGION_SEARCH_QUERIES: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"london|uk|england|scotland|wales|britain", re.I), ["London", "London skyline", "Tower Bridge"]),
    (re.compile(r"paris|france|lyon|nice|marseille", re.I), ["Paris", "Eiffel Tower", "Paris France"]),
    (re.compile(r"rome|milan|venice|florence|italy|naples|tuscany|sicily", re.I), ["Rome", "Venice", "Italy"]),
    (re.compile(r"barcelona|madrid|spain|seville|valencia", re.I), ["Barcelona", "Madrid", "Spain"]),
    (re.compile(r"lisbon|porto|portugal", re.I), ["Lisbon", "Portugal"]),
    (re.compile(r"tokyo|kyoto|osaka|japan", re.I), ["Tokyo", "Kyoto", "Japan"]),
    (re.compile(r"new york|nyc|san francisco|los angeles|chicago|usa|united states", re.I), ["New York City", "San Francisco", "United States"]),
    (re.compile(r"athens|santorini|greece", re.I), ["Athens", "Santorini", "Greece"]),
    (re.compile(r"amsterdam|netherlands|holland", re.I), ["Amsterdam", "Netherlands"]),
    (re.compile(r"berlin|munich|germany", re.I), ["Berlin", "Munich", "Germany"]),
    (re.compile(r"sydney|melbourne|australia", re.I), ["Sydney", "Melbourne", "Australia"]),
]

REGION_FLICKR_TAGS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"london|uk|england|scotland|wales|britain", re.I), "london,england,skyline"),
    (re.compile(r"paris|france", re.I), "paris,france,eiffel"),
    (re.compile(r"rome|milan|venice|florence|italy", re.I), "rome,italy"),
    (re.compile(r"barcelona|madrid|spain", re.I), "barcelona,spain"),
    (re.compile(r"lisbon|porto|portugal", re.I), "lisbon,portugal"),
    (re.compile(r"tokyo|kyoto|osaka|japan", re.I), "tokyo,japan"),
    (re.compile(r"new york|nyc", re.I), "newyork,city"),
    (re.compile(r"san francisco|los angeles|chicago|usa", re.I), "city,skyline,usa"),
    (re.compile(r"athens|santorini|greece", re.I), "santorini,greece"),
    (re.compile(r"amsterdam|netherlands", re.I), "amsterdam,canal"),
    (re.compile(r"berlin|munich|germany", re.I), "berlin,germany"),
    (re.compile(r"sydney|melbourne|australia", re.I), "sydney,australia"),
]


def _cache_key(location: str, code: str) -> str:
    return f"{location.strip().lower()}|{code.strip().lower()}"


def _unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        cleaned = term.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)
    return ordered


def _search_terms(location: str) -> list[str]:
    loc = (location or "").strip()
    if not loc:
        return ["Travel destination"]

    terms: list[str] = []
    for pattern, queries in REGION_SEARCH_QUERIES:
        if pattern.search(loc):
            terms.extend(queries)
            break

    if "," in loc:
        city, country = (part.strip() for part in loc.split(",", 1))
        if city:
            terms.append(city)
            if country:
                terms.append(f"{city} {country}")
    else:
        terms.append(loc)

    terms.append(loc)
    return _unique_terms(terms)


def _flickr_tags(location: str) -> str:
    loc = (location or "").strip()
    for pattern, tags in REGION_FLICKR_TAGS:
        if pattern.search(loc):
            return tags
    city = loc.split(",", 1)[0].strip() if "," in loc else loc
    if city:
        return f"{city},landmark"
    return "travel,landmark"


def _flickr_fallback_url(location: str, code: str) -> str:
    tags = _flickr_tags(location)
    lock = int(hashlib.md5((code or location or "trip").encode()).hexdigest()[:6], 16) % 10000
    return f"https://loremflickr.com/600/400/{tags}?lock={lock}"


def _default_cover_bytes() -> tuple[bytes, str]:
    if DEFAULT_COVER_PATH.is_file():
        return DEFAULT_COVER_PATH.read_bytes(), "image/svg+xml"
    raise HTTPException(status_code=404, detail="Cover image unavailable")


async def _collect_cover_urls(location: str, code: str) -> list[str]:
    urls: list[str] = []
    for term in _search_terms(location):
        photo = await fetch_place_photo(title=term, location=term)
        if photo and photo not in urls:
            urls.append(photo)
    urls.append(_flickr_fallback_url(location, code))
    return urls


async def _download_cover(url: str) -> tuple[bytes, str] | None:
    async with httpx.AsyncClient(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
        response = await client.get(url)
        if response.status_code != 200 or len(response.content) < 1000:
            return None
        media_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
        return response.content, media_type


async def fetch_trip_cover(location: str, code: str) -> tuple[bytes, str]:
    key = _cache_key(location, code)
    if key in _cover_bytes_cache:
        return _cover_bytes_cache[key]

    if key in _cover_url_cache:
        cached = await _download_cover(_cover_url_cache[key])
        if cached:
            _cover_bytes_cache[key] = cached
            return cached

    for url in await _collect_cover_urls(location, code):
        payload = await _download_cover(url)
        if payload:
            _cover_url_cache[key] = url
            if len(_cover_bytes_cache) >= MAX_BYTES_CACHE:
                _cover_bytes_cache.pop(next(iter(_cover_bytes_cache)))
            _cover_bytes_cache[key] = payload
            return payload

    payload = _default_cover_bytes()
    _cover_bytes_cache[key] = payload
    return payload


async def trip_cover_response(location: str = "", code: str = "") -> Response:
    content, media_type = await fetch_trip_cover(location, code)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
