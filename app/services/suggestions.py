"""Suggest activities for a trip location using Wikipedia and OpenStreetMap."""

from dataclasses import dataclass

import httpx

from app.services.geocode import geocode_address

HEADERS = {
    "User-Agent": "ItineraryPlanner/1.0 (friend itinerary app)",
    "Accept": "application/json",
}

WIKI_API = "https://en.wikipedia.org/w/api.php"
OVERPASS_API = "https://overpass-api.de/api/interpreter"

SKIP_TITLES = {
    "city", "town", "village", "country", "district", "borough",
    "united kingdom", "england", "london", "main page",
}

PLACE_HINTS = (
    "museum", "gallery", "park", "garden", "palace", "castle", "cathedral",
    "church", "bridge", "tower", "market", "square", "theatre", "theater",
    "zoo", "aquarium", "stadium", "abbey", "memorial", "monument", "pier",
    "beach", "harbour", "harbor", "station", "quarter", "walk", "trail",
    "experience", "centre", "center", "hall", "house", "ruins", "fort",
)


def _looks_like_place(title: str) -> bool:
    lower = title.lower()
    if any(hint in lower for hint in PLACE_HINTS):
        return True
    words = title.split()
    if len(words) >= 3:
        return True
    if title.endswith(")") or "," in title:
        return True
    return False


@dataclass
class ActivitySuggestion:
    title: str
    location: str
    latitude: float | None
    longitude: float | None
    day_number: int
    url: str | None
    notes: str
    duration_min: int


async def _wikipedia_places(lat: float, lng: float, limit: int = 40) -> list[dict]:
    params = {
        "action": "query",
        "generator": "geosearch",
        "ggscoord": f"{lat}|{lng}",
        "ggsradius": 12000,
        "ggslimit": limit,
        "prop": "coordinates|info",
        "inprop": "url",
        "coprop": "type|name",
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
        response = await client.get(WIKI_API, params=params)
        if response.status_code != 200:
            return []
        data = response.json()

    results = []
    for page in data.get("query", {}).get("pages", {}).values():
        title = page.get("title", "").strip()
        if not title or title.lower() in SKIP_TITLES:
            continue
        if len(title) < 4 or not _looks_like_place(title):
            continue
        coords = page.get("coordinates", [{}])[0]
        results.append({
            "title": title,
            "lat": coords.get("lat"),
            "lng": coords.get("lon"),
            "url": page.get("fullurl"),
        })
    return results


async def _overpass_places(lat: float, lng: float, limit: int = 25) -> list[dict]:
    query = f"""
    [out:json][timeout:25];
    (
      node["tourism"~"attraction|museum|gallery|viewpoint|theme_park"](around:8000,{lat},{lng});
      way["tourism"~"attraction|museum|gallery"](around:8000,{lat},{lng});
      node["leisure"="park"]["name"](around:8000,{lat},{lng});
      node["historic"~"castle|ruins"]["name"](around:8000,{lat},{lng});
    );
    out center {limit};
    """
    async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as client:
        response = await client.post(OVERPASS_API, data={"data": query})
        if response.status_code != 200:
            return []
        data = response.json()

    results = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("tourism") or tags.get("leisure")
        if not name or len(name) < 3:
            continue
        plat = el.get("lat") or el.get("center", {}).get("lat")
        plng = el.get("lon") or el.get("center", {}).get("lon")
        results.append({"title": name, "lat": plat, "lng": plng, "url": None})
    return results


def _dedupe_places(places: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique = []
    for p in places:
        key = p["title"].lower().strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


async def suggest_activities(
    location: str,
    num_days: int = 1,
    per_day: int = 4,
) -> list[ActivitySuggestion]:
    geo = await geocode_address(location)
    if not geo:
        return []

    num_days = max(1, min(num_days, 14))
    target = num_days * per_day

    wiki = await _wikipedia_places(geo.latitude, geo.longitude, limit=target + 20)
    overpass = await _overpass_places(geo.latitude, geo.longitude, limit=target)
    merged = _dedupe_places(overpass + wiki)[:target]

    if not merged:
        return []

    suggestions: list[ActivitySuggestion] = []
    for i, place in enumerate(merged):
        day = (i % num_days) + 1
        title = place["title"]
        suggestions.append(
            ActivitySuggestion(
                title=title,
                location=geo.display_name.split(",")[0] if geo.display_name else location,
                latitude=place.get("lat"),
                longitude=place.get("lng"),
                day_number=day,
                url=place.get("url"),
                notes=f"Suggested for Day {day}",
                duration_min=90 if any(w in title.lower() for w in ("museum", "gallery", "palace")) else 60,
            )
        )
    return suggestions


async def seed_suggested_activities(trip, member_id: str, db) -> int:
    """Create Activity rows from location suggestions. Returns count added."""
    from app.models import Activity
    from app.services.place_photos import fetch_place_photo

    suggestions = await suggest_activities(trip.location, trip.num_days or 1)
    if not suggestions:
        return 0

    existing = {
        a.title.lower().strip()
        for a in db.query(Activity).filter(Activity.trip_id == trip.id).all()
    }
    added = 0

    for s in suggestions:
        key = s.title.lower().strip()
        if key in existing:
            continue
        existing.add(key)

        photo_url = await fetch_place_photo(
            title=s.title,
            location=s.location,
            latitude=s.latitude,
            longitude=s.longitude,
            city_context=trip.location,
        )

        db.add(
            Activity(
                trip_id=trip.id,
                title=s.title,
                url=s.url,
                notes=s.notes,
                location=s.location,
                latitude=s.latitude,
                longitude=s.longitude,
                duration_min=s.duration_min,
                day_number=s.day_number,
                is_suggested=True,
                photo_url=photo_url,
                proposed_by_id=member_id,
            )
        )
        added += 1

    if added:
        db.commit()
    return added
