from dataclasses import dataclass

import httpx

from app.services.distance import Coordinates, haversine_distance

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {
    "User-Agent": "ItineraryPlanner/1.0 (friend itinerary app)",
    "Accept": "application/json",
}

# Min lat, min lng, max lat, max lng — rough bounds for plausibility checks.
COUNTRY_BBOX: dict[str, tuple[float, float, float, float]] = {
    "fr": (41.0, -5.5, 51.5, 10.0),
    "gb": (49.5, -8.5, 61.0, 2.0),
    "es": (35.5, -9.5, 44.0, 4.5),
    "it": (36.0, 6.5, 47.5, 18.5),
    "pt": (36.5, -9.5, 42.5, -6.0),
    "de": (47.0, 5.5, 55.5, 15.5),
    "nl": (50.5, 3.0, 53.8, 7.5),
    "be": (49.4, 2.5, 51.6, 6.5),
    "ch": (45.5, 5.5, 48.0, 10.5),
    "at": (46.0, 9.0, 49.0, 17.5),
    "gr": (34.5, 19.0, 42.0, 29.5),
    "ie": (51.0, -11.0, 55.5, -5.5),
    "jp": (24.0, 122.0, 46.5, 146.0),
    "us": (24.0, -125.0, 49.5, -66.0),
    "ca": (41.5, -141.0, 60.0, -52.0),
    "au": (-44.0, 112.0, -10.0, 154.0),
    "th": (5.0, 97.0, 21.0, 106.0),
    "my": (0.8, 99.6, 7.5, 119.5),
    "vn": (8.0, 102.0, 23.5, 110.0),
    "id": (-11.0, 95.0, 6.5, 141.0),
    "sg": (1.1, 103.6, 1.5, 104.1),
    "kh": (10.0, 102.3, 14.7, 107.6),
}


MAX_ACTIVITY_DISTANCE_KM = 800

COUNTRY_HINTS: tuple[tuple[str, str], ...] = (
    ("france", "fr"),
    ("paris", "fr"),
    ("lyon", "fr"),
    ("marseille", "fr"),
    ("nice", "fr"),
    ("bordeaux", "fr"),
    ("toulouse", "fr"),
    ("corse", "fr"),
    ("corsica", "fr"),
    ("london", "gb"),
    ("uk", "gb"),
    ("england", "gb"),
    ("scotland", "gb"),
    ("wales", "gb"),
    ("edinburgh", "gb"),
    ("manchester", "gb"),
    ("spain", "es"),
    ("barcelona", "es"),
    ("madrid", "es"),
    ("seville", "es"),
    ("sevilla", "es"),
    ("valencia", "es"),
    ("italy", "it"),
    ("rome", "it"),
    ("roma", "it"),
    ("milan", "it"),
    ("milano", "it"),
    ("florence", "it"),
    ("firenze", "it"),
    ("venice", "it"),
    ("napoli", "it"),
    ("naples", "it"),
    ("portugal", "pt"),
    ("lisbon", "pt"),
    ("lisboa", "pt"),
    ("porto", "pt"),
    ("germany", "de"),
    ("berlin", "de"),
    ("munich", "de"),
    ("munchen", "de"),
    ("hamburg", "de"),
    ("netherlands", "nl"),
    ("amsterdam", "nl"),
    ("rotterdam", "nl"),
    ("belgium", "be"),
    ("brussels", "be"),
    ("bruges", "be"),
    ("switzerland", "ch"),
    ("zurich", "ch"),
    ("geneva", "ch"),
    ("austria", "at"),
    ("vienna", "at"),
    ("greece", "gr"),
    ("athens", "gr"),
    ("ireland", "ie"),
    ("dublin", "ie"),
    ("japan", "jp"),
    ("tokyo", "jp"),
    ("kyoto", "jp"),
    ("osaka", "jp"),
    ("usa", "us"),
    ("united states", "us"),
    ("new york", "us"),
    ("nyc", "us"),
    ("san francisco", "us"),
    ("los angeles", "us"),
    ("california", "us"),
    ("chicago", "us"),
    ("canada", "ca"),
    ("toronto", "ca"),
    ("vancouver", "ca"),
    ("montreal", "ca"),
    ("australia", "au"),
    ("sydney", "au"),
    ("melbourne", "au"),
    ("thailand", "th"),
    ("bangkok", "th"),
    ("koh tao", "th"),
    ("phuket", "th"),
    ("chiang mai", "th"),
    ("malaysia", "my"),
    ("kuala lumpur", "my"),
    ("malacca", "my"),
    ("melaka", "my"),
    ("penang", "my"),
    ("georgetown", "my"),
    ("langkawi", "my"),
    ("johor bahru", "my"),
    ("kota kinabalu", "my"),
    ("sabah", "my"),
    ("sarawak", "my"),
    ("vietnam", "vn"),
    ("viet nam", "vn"),
    ("hanoi", "vn"),
    ("ha noi", "vn"),
    ("ho chi minh", "vn"),
    ("saigon", "vn"),
    ("da nang", "vn"),
    ("danang", "vn"),
    ("hoi an", "vn"),
    ("hue", "vn"),
    ("nha trang", "vn"),
    ("ninh binh", "vn"),
    ("hoa lu", "vn"),
    ("halong", "vn"),
    ("ha long", "vn"),
    ("indonesia", "id"),
    ("bali", "id"),
    ("jakarta", "id"),
    ("yogyakarta", "id"),
    ("ubud", "id"),
    ("singapore", "sg"),
    ("cambodia", "kh"),
    ("phnom penh", "kh"),
    ("siem reap", "kh"),
    ("angkor", "kh"),
)

_COUNTRY_NAME_TO_CODE: dict[str, str] = {
    name.casefold(): code
    for code, name in {
        "fr": "France",
        "gb": "United Kingdom",
        "es": "Spain",
        "it": "Italy",
        "pt": "Portugal",
        "de": "Germany",
        "nl": "Netherlands",
        "be": "Belgium",
        "ch": "Switzerland",
        "at": "Austria",
        "gr": "Greece",
        "ie": "Ireland",
        "jp": "Japan",
        "us": "United States",
        "ca": "Canada",
        "au": "Australia",
        "th": "Thailand",
        "my": "Malaysia",
        "vn": "Vietnam",
        "id": "Indonesia",
        "sg": "Singapore",
        "kh": "Cambodia",
    }.items()
}
_COUNTRY_NAME_TO_CODE["uk"] = "gb"
_COUNTRY_NAME_TO_CODE["england"] = "gb"
_COUNTRY_NAME_TO_CODE["scotland"] = "gb"
_COUNTRY_NAME_TO_CODE["wales"] = "gb"
_COUNTRY_NAME_TO_CODE["usa"] = "us"
_COUNTRY_NAME_TO_CODE["united states of america"] = "us"
_COUNTRY_NAME_TO_CODE["viet nam"] = "vn"


@dataclass
class GeocodeResult:
    latitude: float
    longitude: float
    display_name: str


def country_name_to_code(name: str | None) -> str | None:
    text = (name or "").strip().casefold()
    if not text:
        return None
    if text in _COUNTRY_NAME_TO_CODE:
        return _COUNTRY_NAME_TO_CODE[text]
    for label, code in _COUNTRY_NAME_TO_CODE.items():
        if len(label) >= 5 and (label in text or text in label):
            return code
    return None


def infer_country_code(location: str) -> str | None:
    loc = (location or "").lower()
    if not loc:
        return None
    for hint, code in COUNTRY_HINTS:
        if hint in loc:
            return code
    segments = [s.strip() for s in loc.replace(";", ",").split(",") if s.strip()]
    for segment in reversed(segments):
        code = country_name_to_code(segment)
        if code:
            return code
    return None


def infer_country_codes(location: str) -> list[str]:
    """Collect all matching country codes from a location summary."""
    loc = (location or "").lower()
    if not loc:
        return []
    codes: list[str] = []
    seen: set[str] = set()
    for hint, code in COUNTRY_HINTS:
        if hint in loc and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def _trip_destination_names(trip) -> list[str]:
    destinations = getattr(trip, "destinations", None) or []
    names = [d.name.strip() for d in destinations if (getattr(d, "name", None) or "").strip()]
    if names:
        return names

    text = (getattr(trip, "location", None) or "").strip()
    if not text:
        return []
    if " · " in text:
        return [p.strip() for p in text.split(" · ") if p.strip()]
    if ";" in text:
        return [p.strip() for p in text.split(";") if p.strip()]
    return [text]


def _trip_country_codes(trip) -> list[str]:
    destinations = getattr(trip, "destinations", None) or []
    codes: list[str] = []
    seen: set[str] = set()
    if destinations:
        for dest in destinations:
            code = (getattr(dest, "country_code", None) or "").strip().lower()
            if not code:
                code = infer_country_code(getattr(dest, "name", "") or "") or ""
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
        if codes:
            return codes

    for name in _trip_destination_names(trip):
        for code in infer_country_codes(name):
            if code not in seen:
                seen.add(code)
                codes.append(code)
    if codes:
        return codes

    location = (getattr(trip, "location", None) or "").strip()
    return infer_country_codes(location)


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return haversine_distance(
        Coordinates(lat1, lng1),
        Coordinates(lat2, lng2),
    ).kilometers


def _format_display_name(raw: str) -> str:
    return ", ".join(raw.split(",")[:3]).strip()


async def _search_nominatim(
    address: str,
    *,
    countrycodes: str | None = None,
    limit: int = 5,
) -> list[GeocodeResult]:
    address = address.strip()
    if not address:
        return []

    params: dict = {"q": address, "format": "json", "limit": limit}
    if countrycodes:
        params["countrycodes"] = countrycodes

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(NOMINATIM_URL, params=params, headers=HEADERS)
        if response.status_code != 200:
            return []
        data = response.json()

    results: list[GeocodeResult] = []
    for item in data:
        results.append(
            GeocodeResult(
                latitude=float(item["lat"]),
                longitude=float(item["lon"]),
                display_name=_format_display_name(item["display_name"]),
            )
        )
    return results


def _pick_best_result(
    results: list[GeocodeResult],
    anchors: list[GeocodeResult] | None,
) -> GeocodeResult | None:
    if not results:
        return None
    if not anchors:
        return results[0]
    return min(
        results,
        key=lambda r: min(
            _distance_km(a.latitude, a.longitude, r.latitude, r.longitude) for a in anchors
        ),
    )


async def geocode_address(
    address: str,
    *,
    countrycodes: str | None = None,
    near: GeocodeResult | list[GeocodeResult] | None = None,
) -> GeocodeResult | None:
    anchors: list[GeocodeResult] = []
    if isinstance(near, list):
        anchors = near
    elif near is not None:
        anchors = [near]
    results = await _search_nominatim(address, countrycodes=countrycodes, limit=5)
    return _pick_best_result(results, anchors or None)


async def get_trip_anchors(trip) -> list[GeocodeResult]:
    destinations = getattr(trip, "destinations", None) or []
    anchors: list[GeocodeResult] = []

    if destinations:
        for dest in destinations:
            if dest.latitude is not None and dest.longitude is not None:
                anchors.append(
                    GeocodeResult(
                        latitude=dest.latitude,
                        longitude=dest.longitude,
                        display_name=dest.name,
                    )
                )
                continue
            country = (dest.country_code or "").strip().lower() or infer_country_code(dest.name)
            geo = await geocode_address(dest.name, countrycodes=country)
            if geo:
                dest.latitude = geo.latitude
                dest.longitude = geo.longitude
                anchors.append(geo)
        if anchors:
            return anchors

    for name in _trip_destination_names(trip):
        country = infer_country_code(name)
        geo = await geocode_address(name, countrycodes=country)
        if geo:
            anchors.append(geo)
    return anchors


async def get_trip_anchor(trip) -> GeocodeResult | None:
    anchors = await get_trip_anchors(trip)
    return anchors[0] if anchors else None


def _coords_in_country(lat: float, lng: float, country_code: str | None) -> bool:
    if not country_code:
        return True
    bbox = COUNTRY_BBOX.get(country_code)
    if not bbox:
        return True
    min_lat, min_lng, max_lat, max_lng = bbox
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng


def _coords_plausible_for_trip(
    lat: float,
    lng: float,
    anchors: list[GeocodeResult] | None,
    country_codes: list[str] | None = None,
) -> bool:
    codes = [c for c in (country_codes or []) if c]
    if codes and not any(_coords_in_country(lat, lng, code) for code in codes):
        return False
    if not anchors:
        return True
    return any(
        _distance_km(anchor.latitude, anchor.longitude, lat, lng) <= MAX_ACTIVITY_DISTANCE_KM
        for anchor in anchors
    )


def _countrycodes_param(codes: list[str]) -> str | None:
    if not codes:
        return None
    # Nominatim accepts comma-separated ISO codes.
    return ",".join(codes[:5])


async def geocode_for_trip(
    query: str,
    trip,
    *,
    anchor: GeocodeResult | None = None,
) -> GeocodeResult | None:
    text = query.strip()
    if not text:
        return None

    dest_names = _trip_destination_names(trip)
    countries = _trip_country_codes(trip)
    country_param = _countrycodes_param(countries)

    anchors: list[GeocodeResult] = []
    if anchor is not None:
        anchors = [anchor]
    else:
        anchors = await get_trip_anchors(trip)

    attempts: list[str] = []
    for dest in dest_names:
        attempts.append(f"{text}, {dest}")
    attempts.append(text)

    seen: set[str] = set()
    for attempt in attempts:
        key = attempt.lower()
        if key in seen:
            continue
        seen.add(key)
        geo = await geocode_address(attempt, countrycodes=country_param, near=anchors or None)
        if geo and _coords_plausible_for_trip(geo.latitude, geo.longitude, anchors or None, countries):
            return geo
    return None


async def ensure_activity_coordinates(activity, trip) -> bool:
    """Geocode an activity, or fix coords that are far from the trip region."""
    from app.services.day_plan import day_plan_entries

    countries = _trip_country_codes(trip)
    anchors = await get_trip_anchors(trip)
    had_bad_coords = False

    if activity.latitude is not None and activity.longitude is not None:
        if _coords_plausible_for_trip(
            activity.latitude, activity.longitude, anchors or None, countries
        ):
            return False
        activity.latitude = None
        activity.longitude = None
        had_bad_coords = True

    day = activity.day_number or 1
    entries = day_plan_entries(trip)
    day_entry = entries[day - 1] if 1 <= day <= len(entries) else None
    city_context = (day_entry.full_name if day_entry else "").strip()

    queries: list[str] = []
    seen: set[str] = set()
    title = (activity.title or "").strip()
    location = (activity.location or "").strip()

    def add_query(text: str) -> None:
        key = text.strip().lower()
        if key and key not in seen:
            seen.add(key)
            queries.append(text.strip())

    if title and location:
        add_query(f"{title}, {location}")
    if title and city_context and city_context.lower() not in title.lower():
        add_query(f"{title}, {city_context}")
    if location:
        add_query(location)
    if title:
        add_query(title)

    for query in queries:
        geo = await geocode_for_trip(query, trip, anchor=anchors[0] if anchors else None)
        if geo:
            activity.latitude = geo.latitude
            activity.longitude = geo.longitude
            if not location or had_bad_coords:
                activity.location = geo.display_name
            return True

    if had_bad_coords:
        activity.location = None
    return had_bad_coords


async def geocode_confirmed_activities_background(trip_id: str) -> None:
    """Geocode confirmed itinerary activities without holding a DB session during network I/O."""
    from app.database import SessionLocal
    from app.models import Activity, Trip
    from sqlalchemy.orm import joinedload

    db = SessionLocal()
    trip: Trip | None = None
    activities: list[Activity] = []
    try:
        trip = (
            db.query(Trip)
            .options(joinedload(Trip.destinations))
            .filter(Trip.id == trip_id)
            .first()
        )
        if not trip:
            return

        activities = (
            db.query(Activity)
            .filter(
                Activity.trip_id == trip.id,
                Activity.is_suggested.is_(False),
            )
            .all()
        )
        if not activities:
            return

        # Eagerly load destinations, then detach by closing the session (no expunge).
        list(trip.destinations)
        activities = list(activities)
    except Exception:
        return
    finally:
        db.close()

    if not trip:
        return

    updated = False
    try:
        for activity in activities:
            if await ensure_activity_coordinates(activity, trip):
                updated = True
    except Exception:
        return

    if not updated:
        return

    db = SessionLocal()
    try:
        for activity in activities:
            row = db.query(Activity).filter(Activity.id == activity.id).first()
            if not row:
                continue
            row.latitude = activity.latitude
            row.longitude = activity.longitude
            row.location = activity.location
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
