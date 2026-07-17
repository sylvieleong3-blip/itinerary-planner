"""Backpack-style route planner: countries → cities → days per city."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.models import Trip, TripDestination
from app.services.destinations import (
    MAX_DESTINATIONS,
    country_label,
    format_location_summary_by_country,
    shorten_city_name,
)
from app.services.geocode import country_name_to_code, infer_country_code


@dataclass
class RouteCity:
    name: str
    days: int
    country_code: str | None = None


@dataclass
class RouteCountry:
    name: str
    code: str | None
    cities: list[RouteCity]


def compute_start_days(day_counts: list[int]) -> list[int]:
    """Map per-city day counts to 1-based start_day values."""
    starts: list[int] = []
    day = 1
    for count in day_counts:
        starts.append(day)
        day += max(1, count)
    return starts


def parse_route_plan(raw: str | dict | list | None) -> list[RouteCountry]:
    """Parse JSON route plan from the visual planner form."""
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid route plan.") from exc
    else:
        data = raw

    countries_raw: list[Any]
    if isinstance(data, dict):
        if data.get("mode") == "simple":
            cities_raw = data.get("cities") or []
            if not cities_raw:
                raise ValueError("Add at least one city with days.")
            code = None
            name = ""
            cities: list[RouteCity] = []
            for city in cities_raw:
                if not isinstance(city, dict):
                    continue
                city_name = (city.get("name") or "").strip()
                if not city_name:
                    continue
                try:
                    days = int(city.get("days") or 1)
                except (TypeError, ValueError):
                    days = 1
                days = max(1, days)
                city_code = (city.get("country_code") or "").strip().lower() or infer_country_code(city_name)
                if not code and city_code:
                    code = city_code
                    name = country_label(code)
                cities.append(RouteCity(name=city_name, days=days, country_code=city_code or code))
                if len(cities) > MAX_DESTINATIONS:
                    raise ValueError(f"Add at most {MAX_DESTINATIONS} cities.")
            if not cities:
                raise ValueError("Add at least one city with days.")
            if not name:
                name = country_label(code)
            return [RouteCountry(name=name or "Other", code=code, cities=cities)]
        countries_raw = data.get("countries") or []
    elif isinstance(data, list):
        countries_raw = data
    else:
        raise ValueError("Invalid route plan.")

    countries: list[RouteCountry] = []
    city_count = 0

    for group in countries_raw:
        if not isinstance(group, dict):
            continue
        code = (group.get("code") or "").strip().lower() or None
        name = (group.get("name") or "").strip()
        if not name and code:
            name = country_label(code)
        if not code and name:
            code = country_name_to_code(name) or infer_country_code(name)

        cities: list[RouteCity] = []
        for city in group.get("cities") or []:
            if not isinstance(city, dict):
                continue
            city_name = (city.get("name") or "").strip()
            if not city_name:
                continue
            try:
                days = int(city.get("days") or 1)
            except (TypeError, ValueError):
                days = 1
            days = max(1, days)
            city_code = (city.get("country_code") or code or "").strip().lower() or None
            if not city_code:
                city_code = infer_country_code(city_name)
            cities.append(RouteCity(name=city_name, days=days, country_code=city_code))
            city_count += 1
            if city_count > MAX_DESTINATIONS:
                raise ValueError(f"Add at most {MAX_DESTINATIONS} cities.")

        if cities:
            if not name:
                name = country_label(code)
            countries.append(RouteCountry(name=name, code=code, cities=cities))

    if not countries:
        raise ValueError("Add at least one city with days.")
    return countries


def flatten_route_plan(plan: list[RouteCountry]) -> list[tuple[str, str | None, int, int]]:
    """Return (city_name, country_code, days, start_day) in route order."""
    day_counts = [city.days for country in plan for city in country.cities]
    starts = compute_start_days(day_counts)
    items: list[tuple[str, str | None, int, int]] = []
    idx = 0
    for country in plan:
        for city in country.cities:
            code = city.country_code or country.code
            items.append((city.name, code, city.days, starts[idx]))
            idx += 1
    return items


def sync_trip_from_route_plan(trip: Trip, raw: str | dict | list | None) -> int:
    """Create TripDestination rows from route plan; return total num_days."""
    plan = parse_route_plan(raw)
    items = flatten_route_plan(plan)

    sorted_pairs = [(name, code) for name, code, _, _ in items]
    trip.location = format_location_summary_by_country(sorted_pairs)
    trip.destinations.clear()

    for i, (name, code, _days, start_day) in enumerate(items):
        trip.destinations.append(
            TripDestination(
                name=name,
                country_code=code,
                sort_order=i,
                start_day=start_day,
            )
        )

    total = sum(days for _name, _code, days, _start in items)
    trip.num_days = max(1, total)
    return trip.num_days


def trip_to_route_plan(trip: Trip) -> dict:
    """Serialize existing trip destinations for edit-form prefill."""
    destinations = getattr(trip, "destinations", None) or []
    num_days = max(1, trip.num_days or 1)

    if not destinations:
        names = (trip.location or "").strip()
        if names:
            code = infer_country_code(names)
            return {
                "countries": [
                    {
                        "name": country_label(code) if code else "",
                        "code": code,
                        "cities": [{"name": names, "days": num_days}],
                    }
                ]
            }
        return {
            "countries": [
                {
                    "name": "",
                    "code": None,
                    "cities": [{"name": "", "days": 3}],
                }
            ]
        }

    ordered = sorted(destinations, key=lambda d: (d.sort_order, d.start_day or 1, d.name))
    countries: list[dict] = []

    for i, dest in enumerate(ordered):
        start = dest.start_day or 1
        if i + 1 < len(ordered):
            days = max(1, (ordered[i + 1].start_day or 1) - start)
        else:
            days = max(1, num_days - start + 1)

        code = (dest.country_code or "").strip().lower() or infer_country_code(dest.name)
        name = country_label(code) if code else "Other"

        city_entry = {"name": dest.name, "days": days}
        if countries and countries[-1]["code"] == code:
            countries[-1]["cities"].append(city_entry)
        else:
            countries.append({"name": name, "code": code, "cities": [city_entry]})

    if len(countries) == 1 and len(countries[0]["cities"]) <= 3:
        return {
            "mode": "simple",
            "cities": [
                {"name": c["name"], "days": c["days"]}
                for c in countries[0]["cities"]
            ],
        }

    return {"countries": countries}


def route_plan_timeline(plan: list[RouteCountry]) -> list[dict]:
    """Day-range preview rows for templates/tests."""
    rows: list[dict] = []
    for name, code, days, start in flatten_route_plan(plan):
        end = start + days - 1
        rows.append(
            {
                "city": shorten_city_name(name, code),
                "country_code": code,
                "days": days,
                "start_day": start,
                "end_day": end,
            }
        )
    return rows
