"""Helpers for multi-city / multi-country trip destinations."""

from __future__ import annotations

from app.models import Trip, TripDestination
from app.services.geocode import country_name_to_code, infer_country_code

LOCATION_SEPARATOR = " · "
MAX_DESTINATIONS = 8

# Alternate spellings and sub-cities → canonical display name.
CITY_NAME_ALIASES: dict[str, str] = {
    "corscia": "Corsica",
    "corse": "Corsica",
    "ajaccio": "Corsica",
    "bastia": "Corsica",
    "bonifacio": "Corsica",
    "calvi": "Corsica",
    "porto-vecchio": "Corsica",
    "corte": "Corsica",
    "propriano": "Corsica",
    "saint-florent": "Corsica",
    "melaka": "Malacca",
    "georgetown": "George Town",
    "penang": "George Town",
    "kl": "Kuala Lumpur",
    "roma": "Rome",
    "nyc": "New York",
    "sf": "San Francisco",
    "saigon": "Ho Chi Minh City",
}


def canonical_destination_name(name: str) -> str:
    """Fix common typos and normalize city labels for storage/display."""
    text = (name or "").strip()
    if not text:
        return text
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        return text
    first = parts[0]
    alias = CITY_NAME_ALIASES.get(first.casefold())
    if alias:
        parts[0] = alias
    return ", ".join(parts)

COUNTRY_NAMES: dict[str, str] = {
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
}


def country_label(code: str | None) -> str:
    if not code:
        return "Other"
    return COUNTRY_NAMES.get(code.lower(), code.upper())


def normalize_destination_names(raw: list[str] | None) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for item in raw or []:
        name = canonical_destination_name((item or "").strip())
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
        if len(names) >= MAX_DESTINATIONS:
            break
    return names


def _destination_pairs(trip: Trip) -> list[tuple[str, str | None]]:
    destinations = getattr(trip, "destinations", None) or []
    return [(d.name, d.country_code) for d in sorted(destinations, key=lambda d: d.sort_order)]


def _unique_city_labels(pairs: list[tuple[str, str | None]]) -> set[str]:
    return {shorten_city_name(name, code).casefold() for name, code in pairs if (name or "").strip()}


def backfill_destination_names(trip: Trip) -> bool:
    """Correct stored destination names (e.g. Corscia → Corsica) on existing trips."""
    changed = False
    for dest in getattr(trip, "destinations", None) or []:
        fixed = canonical_destination_name(dest.name)
        if fixed and fixed != dest.name:
            dest.name = fixed
            changed = True
    if backfill_location_summary(trip):
        changed = True
    return changed


def backfill_location_summary(trip: Trip) -> bool:
    """Refresh trip.location from destinations (dedupes cities, plain label for single-city trips)."""
    pairs = _destination_pairs(trip)
    if not pairs:
        return False
    new_location = format_location_summary_by_country(pairs)
    if new_location == (trip.location or ""):
        return False
    trip.location = new_location
    return True


def shorten_city_name(name: str, country_code: str | None = None) -> str:
    """Prefer a short city label when autocomplete returns 'City, Country'."""
    text = (name or "").strip()
    if not text:
        return text

    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) <= 1:
        return text

    country_names = {v.casefold() for v in COUNTRY_NAMES.values()}
    if country_code:
        country_names.add(country_label(country_code).casefold())

    # Drop trailing country / region crumbs that duplicate the country group.
    while len(parts) > 1 and (
        parts[-1].casefold() in country_names
        or infer_country_code(parts[-1]) == country_code
        or (country_code and parts[-1].casefold() == country_code.casefold())
    ):
        parts.pop()

    return parts[0] if len(parts) == 1 else ", ".join(parts)


def sort_destinations_by_country(
    names: list[str],
    country_names: list[str] | None = None,
) -> list[tuple[str, str | None]]:
    """Group cities by country; sort countries A–Z, cities A–Z within each."""
    country_names = country_names or []
    tagged: list[tuple[str, str | None, int]] = []

    for index, name in enumerate(names):
        country_name = country_names[index].strip() if index < len(country_names) else ""
        code = country_name_to_code(country_name) or infer_country_code(name)
        tagged.append((name, code, index))

    tagged.sort(
        key=lambda item: (
            country_label(item[1]).casefold() if item[1] else "zzzz",
            shorten_city_name(item[0], item[1]).casefold(),
            item[2],
        )
    )
    return [(name, code) for name, code, _ in tagged]


def format_location_summary(names: list[str]) -> str:
    return LOCATION_SEPARATOR.join(names)


def format_location_summary_by_country(destinations: list[tuple[str, str | None]]) -> str:
    if not destinations:
        return ""
    if len(destinations) == 1:
        name, code = destinations[0]
        return shorten_city_name(name, code)

    if len(_unique_city_labels(destinations)) == 1:
        name, code = destinations[0]
        return shorten_city_name(name, code)

    groups: list[tuple[str | None, list[str]]] = []
    for name, code in destinations:
        short = shorten_city_name(name, code)
        if groups and groups[-1][0] == code:
            if short not in groups[-1][1]:
                groups[-1][1].append(short)
        else:
            groups.append((code, [short]))

    if len(groups) == 1 and groups[0][0] is None:
        return format_location_summary(groups[0][1])

    parts: list[str] = []
    for code, cities in groups:
        city_text = ", ".join(cities)
        if code:
            parts.append(f"{country_label(code)}: {city_text}")
        else:
            parts.append(city_text)
    return LOCATION_SEPARATOR.join(parts)


def parse_location_summary(location: str | None) -> list[str]:
    text = (location or "").strip()
    if not text:
        return []
    if LOCATION_SEPARATOR in text:
        parts = text.split(LOCATION_SEPARATOR)
    elif ";" in text:
        parts = text.split(";")
    else:
        return [text]

    names: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # "France: Paris, Lyon" → extract cities
        if ": " in part:
            maybe_cities = part.split(": ", 1)[1]
            for city in maybe_cities.split(","):
                city = city.strip()
                if city:
                    names.append(city)
        else:
            names.append(part)
    return normalize_destination_names(names)


def trip_destination_names(trip: Trip) -> list[str]:
    destinations = getattr(trip, "destinations", None) or []
    if destinations:
        ordered = sorted(destinations, key=lambda d: (d.sort_order, d.start_day or 1, d.name))
        return [d.name for d in ordered if (d.name or "").strip()]
    return parse_location_summary(trip.location)


def trip_country_codes(trip: Trip) -> list[str]:
    destinations = getattr(trip, "destinations", None) or []
    codes: list[str] = []
    seen: set[str] = set()

    if destinations:
        ordered = sorted(destinations, key=lambda d: (d.sort_order, d.start_day or 1, d.name))
        for dest in ordered:
            code = (dest.country_code or "").strip().lower() or infer_country_code(dest.name)
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
        return codes

    for name in trip_destination_names(trip):
        code = infer_country_code(name)
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def trip_country_codes_csv(trip: Trip) -> str:
    return ",".join(trip_country_codes(trip)[:5])


def destinations_by_country(trip: Trip) -> list[dict]:
    """Grouped route for plan UI: [{code, name, cities, start_day, end_day}]."""
    destinations = getattr(trip, "destinations", None) or []
    num_days = max(1, trip.num_days or 1)

    if destinations:
        ordered = sorted(destinations, key=lambda d: (d.sort_order, d.start_day or 1, d.name))
        items = [
            {
                "name": shorten_city_name(
                    d.name,
                    (d.country_code or "").strip().lower() or infer_country_code(d.name),
                ),
                "full_name": d.name,
                "code": (d.country_code or "").strip().lower() or infer_country_code(d.name),
                "start_day": d.start_day or 1,
            }
            for d in ordered
            if (d.name or "").strip()
        ]
    else:
        names = trip_destination_names(trip)
        sorted_pairs = sort_destinations_by_country(names) if names else []
        starts = _assign_start_days(len(sorted_pairs), num_days) if sorted_pairs else []
        items = [
            {
                "name": shorten_city_name(name, code),
                "full_name": name,
                "code": code,
                "start_day": starts[i],
            }
            for i, (name, code) in enumerate(sorted_pairs)
        ]

    if not items:
        return []

    groups: list[dict] = []
    for item in items:
        code = item["code"]
        if groups and groups[-1]["code"] == code:
            groups[-1]["cities"].append(item["name"])
        else:
            groups.append(
                {
                    "code": code,
                    "name": country_label(code),
                    "cities": [item["name"]],
                    "start_day": item["start_day"],
                    "end_day": item["start_day"],
                }
            )

    for i, group in enumerate(groups):
        next_start = groups[i + 1]["start_day"] if i + 1 < len(groups) else num_days + 1
        group["end_day"] = max(group["start_day"], next_start - 1)

    return groups


def destination_for_day(trip: Trip, day: int) -> str:
    destinations = getattr(trip, "destinations", None) or []
    names = [d.name for d in destinations if (d.name or "").strip()] if destinations else trip_destination_names(trip)
    if not names:
        return (trip.location or "").strip()
    if len(names) == 1:
        only = names[0]
        code = None
        if destinations:
            code = (destinations[0].country_code or "").strip().lower() or infer_country_code(only)
        else:
            code = infer_country_code(only)
        return shorten_city_name(only, code)

    if destinations:
        ordered = sorted(destinations, key=lambda d: (d.start_day or 1, d.sort_order, d.name))
        current = ordered[0]
        for dest in ordered:
            start = dest.start_day or 1
            if day >= start:
                current = dest
            else:
                break
        code = (current.country_code or "").strip().lower() or infer_country_code(current.name)
        return shorten_city_name(current.name, code)

    num_days = max(1, trip.num_days or 1)
    idx = min(len(names) - 1, ((max(1, day) - 1) * len(names)) // num_days)
    name = names[idx]
    return shorten_city_name(name, infer_country_code(name))


def country_for_day(trip: Trip, day: int) -> dict:
    destinations = getattr(trip, "destinations", None) or []
    city = destination_for_day(trip, day)
    code = None
    if destinations:
        ordered = sorted(destinations, key=lambda d: (d.start_day or 1, d.sort_order, d.name))
        current = ordered[0] if ordered else None
        for dest in ordered:
            start = dest.start_day or 1
            if day >= start:
                current = dest
            else:
                break
        if current is not None:
            code = (current.country_code or "").strip().lower() or infer_country_code(current.name)
    if not code:
        code = infer_country_code(city)
    return {"code": code, "name": country_label(code), "city": city}


def _assign_start_days(count: int, num_days: int) -> list[int]:
    num_days = max(1, num_days)
    if count <= 1:
        return [1]
    starts: list[int] = []
    for i in range(count):
        starts.append(1 + (i * num_days) // count)
    return starts


def backfill_destination_country_codes(trip: Trip) -> bool:
    """Persist inferred country codes for destinations missing them."""
    changed = False
    for dest in getattr(trip, "destinations", None) or []:
        if (dest.country_code or "").strip():
            continue
        code = infer_country_code(dest.name)
        if code:
            dest.country_code = code
            changed = True
    return changed


def sync_trip_destinations(
    trip: Trip,
    names: list[str],
    *,
    num_days: int | None = None,
    country_names: list[str] | None = None,
) -> None:
    clean = normalize_destination_names(names)
    if not clean:
        raise ValueError("Add at least one destination.")

    sorted_pairs = sort_destinations_by_country(clean, country_names)
    days = max(1, num_days if num_days is not None else (trip.num_days or 1))
    starts = _assign_start_days(len(sorted_pairs), days)
    trip.location = format_location_summary_by_country(sorted_pairs)

    trip.destinations.clear()

    for i, (name, code) in enumerate(sorted_pairs):
        trip.destinations.append(
            TripDestination(
                name=name,
                country_code=code,
                sort_order=i,
                start_day=starts[i],
            )
        )
