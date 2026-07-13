"""Trip weather via Open-Meteo (free, no API key)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from app.services.dates import day_iso_date


@dataclass
class DayWeather:
    icon: str
    temp_c: int | None
    label: str


def weather_code_to_icon(code: int) -> str:
    if code in (0, 1):
        return "sun"
    if code in (2, 3):
        return "cloud"
    if code in (45, 48):
        return "fog"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "storm"
    return "cloud"


def weather_label(icon: str, temp_c: int | None) -> str:
    names = {
        "sun": "Sunny",
        "cloud": "Cloudy",
        "fog": "Foggy",
        "rain": "Rainy",
        "snow": "Snowy",
        "storm": "Storms",
    }
    base = names.get(icon, "Weather")
    if temp_c is None:
        return base
    return f"{base}, {temp_c}°C"


async def _geocode_open_meteo(location: str) -> tuple[float, float] | None:
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location.strip(), "count": 1, "language": "en", "format": "json"},
        )
        if response.status_code != 200:
            return None
        results = response.json().get("results") or []
        if not results:
            return None
        item = results[0]
        return float(item["latitude"]), float(item["longitude"])


async def _resolve_coords(location: str) -> tuple[float, float] | None:
    location = location.strip()
    if not location:
        return None

    queries = [location]
    if "," in location:
        queries.append(location.split(",")[0].strip())

    for query in queries:
        if not query:
            continue
        coords = await _geocode_open_meteo(query)
        if coords:
            return coords

    from app.services.geocode import geocode_address

    result = await geocode_address(location)
    if result:
        return result.latitude, result.longitude
    return None


async def fetch_trip_weather(
    location: str,
    start_date: str,
    num_days: int,
) -> dict[int, DayWeather]:
    coords = await _resolve_coords(location)
    if not coords:
        return {}

    lat, lng = coords
    start_iso = day_iso_date(start_date, 1)
    if not start_iso:
        return {}

    try:
        start = datetime.strptime(start_iso, "%Y-%m-%d")
        end = start + timedelta(days=max(1, num_days) - 1)
    except ValueError:
        return {}

    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lng,
                "daily": "weather_code,temperature_2m_max",
                "timezone": "auto",
                "start_date": start_iso,
                "end_date": end.strftime("%Y-%m-%d"),
            },
        )
        if response.status_code != 200:
            return {}

        daily = response.json().get("daily") or {}
        dates = daily.get("time") or []
        codes = daily.get("weather_code") or []
        temps = daily.get("temperature_2m_max") or []

    by_date: dict[str, DayWeather] = {}
    for i, date_str in enumerate(dates):
        code = int(codes[i]) if i < len(codes) and codes[i] is not None else 3
        temp_raw = temps[i] if i < len(temps) else None
        temp_c = round(temp_raw) if temp_raw is not None else None
        icon = weather_code_to_icon(code)
        by_date[date_str] = DayWeather(icon=icon, temp_c=temp_c, label=weather_label(icon, temp_c))

    result: dict[int, DayWeather] = {}
    for day in range(1, num_days + 1):
        iso = day_iso_date(start_date, day)
        if iso and iso in by_date:
            result[day] = by_date[iso]
    return result
