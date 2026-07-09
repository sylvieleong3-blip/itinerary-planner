"""Fetch location photos from Wikipedia / Wikimedia Commons (free, no API key)."""

from urllib.parse import quote

import httpx

HEADERS = {
    "User-Agent": "GroupDayPlanner/1.0 (friend itinerary app; contact@example.com)",
    "Accept": "application/json",
}

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_REST = "https://en.wikipedia.org/api/rest_v1/page/summary"
THUMB_SIZE = 800
GEO_RADIUS_M = 750


async def _wiki_get(params: dict) -> dict | None:
    async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
        response = await client.get(WIKI_API, params={**params, "format": "json"})
        if response.status_code != 200:
            return None
        return response.json()


def _extract_thumbnail(data: dict) -> str | None:
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        if page.get("missing"):
            continue
        thumb = page.get("thumbnail", {}).get("source")
        if thumb:
            return thumb
        original = page.get("original", {}).get("source")
        if original:
            return original
    return None


async def _photo_by_coordinates(lat: float, lng: float) -> str | None:
    data = await _wiki_get({
        "action": "query",
        "generator": "geosearch",
        "ggscoord": f"{lat}|{lng}",
        "ggsradius": GEO_RADIUS_M,
        "ggslimit": 8,
        "prop": "pageimages",
        "piprop": "thumbnail|original",
        "pithumbsize": THUMB_SIZE,
    })
    if not data:
        return None
    return _extract_thumbnail(data)


async def _photo_by_search(query: str) -> str | None:
    query = query.strip()
    if not query:
        return None

    data = await _wiki_get({
        "action": "query",
        "generator": "search",
        "gssearch": query,
        "gslimit": 5,
        "prop": "pageimages",
        "piprop": "thumbnail|original",
        "pithumbsize": THUMB_SIZE,
    })
    if not data:
        return None
    return _extract_thumbnail(data)


async def _photo_by_title(title: str) -> str | None:
    slug = quote(title.replace(" ", "_"), safe="(),%")
    async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
        response = await client.get(f"{WIKI_REST}/{slug}")
        if response.status_code != 200:
            return None
        data = response.json()
        thumb = data.get("thumbnail", {}).get("source")
        if thumb:
            return thumb
        original = data.get("originalimage", {}).get("source")
        return original


async def fetch_place_photo(
    *,
    title: str,
    location: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    city_context: str | None = None,
) -> str | None:
    """
    Find a photo for a place using Wikipedia / Wikimedia.
    Tries coordinates first, then location name, then activity title.
    """
    if latitude is not None and longitude is not None:
        photo = await _photo_by_coordinates(latitude, longitude)
        if photo:
            return photo

    search_queries: list[str] = []
    if location:
        search_queries.append(location)
        if city_context and city_context.lower() not in location.lower():
            search_queries.append(f"{location} {city_context}")
    if title:
        search_queries.append(title)
        if city_context:
            search_queries.append(f"{title} {city_context}")

    seen: set[str] = set()
    for query in search_queries:
        if query in seen:
            continue
        seen.add(query)

        photo = await _photo_by_search(query)
        if photo:
            return photo

        photo = await _photo_by_title(query)
        if photo:
            return photo

    return None
