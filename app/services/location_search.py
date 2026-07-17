"""Free location typeahead via Photon (OpenStreetMap data)."""

import httpx

PHOTON_URL = "https://photon.komoot.io/api/"
HEADERS = {"User-Agent": "ItineraryPlanner/1.0 (friend itinerary app)"}


def _feature_label(properties: dict) -> str:
    parts: list[str] = []
    for key in ("name", "street", "housenumber", "city", "state", "country"):
        value = (properties.get(key) or "").strip()
        if not value:
            continue
        if parts and value.lower() == parts[-1].lower():
            continue
        if any(value.lower() == p.lower() for p in parts):
            continue
        parts.append(value)
    return ", ".join(parts[:4]) if parts else "Unknown place"


async def search_locations(
    query: str,
    *,
    country: str | None = None,
    search_type: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    limit: int = 6,
) -> list[dict]:
    text = query.strip()
    if len(text) < 2:
        return []

    params: dict = {"q": text, "limit": str(min(limit, 8)), "lang": "en"}
    if lat is not None and lon is not None:
        params["lat"] = str(lat)
        params["lon"] = str(lon)
    if search_type == "city":
        params["layer"] = "city"

    async with httpx.AsyncClient(timeout=8.0, headers=HEADERS) as client:
        response = await client.get(PHOTON_URL, params=params)
        if response.status_code != 200:
            return []
        data = response.json()

    results: list[dict] = []
    allowed_countries = {
        c.strip().lower()
        for c in (country or "").split(",")
        if c.strip()
    }

    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        feature_country = (props.get("countrycode") or "").lower()
        osm_type = (props.get("type") or "").lower()
        osm_key = (props.get("osm_key") or "").lower()
        osm_value = (props.get("osm_value") or "").lower()

        if search_type == "country":
            if osm_key != "place" or osm_value not in ("country", "state"):
                if osm_type not in ("country", "state"):
                    continue

        if allowed_countries and feature_country not in allowed_countries:
            continue

        coords = feature.get("geometry", {}).get("coordinates") or []
        if len(coords) < 2:
            continue

        lng, lat_val = float(coords[0]), float(coords[1])
        if search_type == "country":
            label = (props.get("name") or props.get("country") or "").strip()
            if not label:
                continue
        else:
            label = _feature_label(props)
        results.append({
            "label": label,
            "latitude": lat_val,
            "longitude": lng,
            "name": props.get("name") or label,
            "country": props.get("country"),
            "countrycode": feature_country or None,
        })
        if len(results) >= limit:
            break

    return results
