import math
from dataclasses import dataclass


@dataclass
class Coordinates:
    latitude: float
    longitude: float


@dataclass
class DistanceResult:
    miles: float
    kilometers: float
    walking_minutes: int
    driving_minutes: int


EARTH_RADIUS_MI = 3958.8
EARTH_RADIUS_KM = 6371


def haversine_distance(from_coord: Coordinates, to_coord: Coordinates) -> DistanceResult:
    d_lat = math.radians(to_coord.latitude - from_coord.latitude)
    d_lng = math.radians(to_coord.longitude - from_coord.longitude)
    lat1 = math.radians(from_coord.latitude)
    lat2 = math.radians(to_coord.latitude)

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    miles = EARTH_RADIUS_MI * c
    kilometers = EARTH_RADIUS_KM * c

    return DistanceResult(
        miles=miles,
        kilometers=kilometers,
        walking_minutes=round((miles / 3) * 60),
        driving_minutes=round((miles / 25) * 60),
    )


def format_distance(result: DistanceResult) -> str:
    if result.miles < 0.1:
        return "< 0.1 mi"
    if result.miles < 1:
        return f"{result.miles:.1f} mi"
    return f"{result.miles:.1f} mi ({result.kilometers:.1f} km)"


def format_travel_time(result: DistanceResult) -> str:
    if result.miles < 0.05:
        return "Same block"
    if result.walking_minutes <= 15:
        return f"~{result.walking_minutes} min walk"
    return f"~{result.driving_minutes} min drive"


def has_coordinates(lat: float | None, lng: float | None) -> bool:
    return lat is not None and lng is not None


def maps_url(lat: float, lng: float, label: str | None = None) -> str:
    q = label or f"{lat},{lng}"
    from urllib.parse import quote

    return f"https://www.google.com/maps/search/?api=1&query={quote(q)}"


def maps_link_for_activity(activity) -> str | None:
    """Google Maps URL for an activity, using coordinates or address."""
    lat = getattr(activity, "latitude", None)
    lng = getattr(activity, "longitude", None)
    location = getattr(activity, "location", None)
    title = getattr(activity, "title", None)

    if lat is not None and lng is not None:
        return maps_url(lat, lng, location or title)
    if location:
        return maps_url(0, 0, location)
    return None


def directions_url(from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> str:
    return (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={from_lat},{from_lng}&destination={to_lat},{to_lng}&travelmode=walking"
    )


def normalize_time_24(value: str | None, default: str = "12:00") -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    parts = raw.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return default
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return f"{hour:02d}:{minute:02d}"


def parse_duration_min(value: str | int | None, default: int = 60) -> int:
    if value is None:
        return default
    raw = str(value).strip()
    if not raw:
        return default
    try:
        duration = int(raw)
    except ValueError:
        return default
    return max(15, duration)


def parse_optional_duration_min(value: str | int | None) -> int:
    if value is None:
        return 0
    raw = str(value).strip()
    if not raw:
        return 0
    try:
        duration = int(raw)
    except ValueError:
        return 0
    if duration <= 0:
        return 0
    return max(15, duration)


def format_time_12h(time_24: str | None) -> str:
    normalized = normalize_time_24(time_24, default="")
    if not normalized:
        return ""
    hour, minute = map(int, normalized.split(":"))
    period = "PM" if hour >= 12 else "AM"
    display_hour = hour % 12 or 12
    return f"{display_hour}:{minute:02d} {period}"
