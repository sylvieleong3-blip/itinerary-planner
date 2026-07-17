"""Reorder, add, and remove trip days and country segments."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Activity, Trip, TripDestination
from app.services.destinations import (
    country_for_day,
    country_label,
    format_location_summary_by_country,
    shorten_city_name,
)
from app.services.geocode import infer_country_code


@dataclass
class DayPlanEntry:
    city: str
    full_name: str
    country_code: str | None


def _destination_row_for_day(trip: Trip, day: int) -> TripDestination | None:
    destinations = getattr(trip, "destinations", None) or []
    if not destinations:
        return None
    ordered = sorted(destinations, key=lambda d: (d.start_day or 1, d.sort_order, d.name))
    current = ordered[0]
    for dest in ordered:
        if day >= (dest.start_day or 1):
            current = dest
        else:
            break
    return current


def day_plan_entries(trip: Trip) -> list[DayPlanEntry]:
    num_days = max(1, trip.num_days or 1)
    entries: list[DayPlanEntry] = []
    for day in range(1, num_days + 1):
        dest = _destination_row_for_day(trip, day)
        if dest and (dest.name or "").strip():
            code = (dest.country_code or "").strip().lower() or infer_country_code(dest.name)
            entries.append(
                DayPlanEntry(
                    city=shorten_city_name(dest.name, code),
                    full_name=dest.name.strip(),
                    country_code=code,
                )
            )
        else:
            info = country_for_day(trip, day)
            entries.append(
                DayPlanEntry(
                    city=info["city"],
                    full_name=info["city"],
                    country_code=info["code"],
                )
            )
    return entries


def persist_day_plan(trip: Trip, entries: list[DayPlanEntry]) -> None:
    if not entries:
        raise ValueError("A trip needs at least one day.")

    trip.destinations.clear()
    pairs: list[tuple[str, str | None]] = []
    for index, entry in enumerate(entries):
        trip.destinations.append(
            TripDestination(
                name=entry.full_name,
                country_code=entry.country_code,
                sort_order=index,
                start_day=index + 1,
            )
        )
        pairs.append((entry.full_name, entry.country_code))

    trip.num_days = len(entries)
    trip.location = format_location_summary_by_country(pairs)


def _remap_activity_days(trip: Trip, mapping: dict[int, int]) -> None:
    for activity in trip.activities:
        old_day = activity.day_number or 1
        if old_day in mapping:
            activity.day_number = mapping[old_day]


def _delete_activities_on_days(db: Session, trip: Trip, days: set[int]) -> None:
    for activity in list(trip.activities):
        if (activity.day_number or 1) in days:
            db.delete(activity)


def reorder_days(trip: Trip, new_order: list[int]) -> None:
    """new_order maps new position -> old day number, e.g. [2, 3, 1]."""
    num_days = max(1, trip.num_days or 1)
    expected = list(range(1, num_days + 1))
    if sorted(new_order) != expected:
        raise ValueError("Invalid day order.")

    entries = day_plan_entries(trip)
    reordered = [entries[old_day - 1] for old_day in new_order]
    old_to_new = {old_day: index + 1 for index, old_day in enumerate(new_order)}

    _remap_activity_days(trip, old_to_new)
    persist_day_plan(trip, reordered)


def delete_day(db: Session, trip: Trip, day_number: int) -> None:
    num_days = max(1, trip.num_days or 1)
    day_number = max(1, min(int(day_number), num_days))
    if num_days <= 1:
        raise ValueError("Cannot delete the only day.")

    entries = day_plan_entries(trip)
    remaining = [entry for index, entry in enumerate(entries) if index + 1 != day_number]

    _delete_activities_on_days(db, trip, {day_number})

    mapping: dict[int, int] = {}
    new_day = 1
    for old_day in range(1, num_days + 1):
        if old_day == day_number:
            continue
        mapping[old_day] = new_day
        new_day += 1
    _remap_activity_days(trip, mapping)
    persist_day_plan(trip, remaining)


def delete_country(db: Session, trip: Trip, country_code: str) -> None:
    code = (country_code or "").strip().lower()
    if not code:
        raise ValueError("Unknown country.")

    entries = day_plan_entries(trip)
    removed_days = {
        index + 1
        for index, entry in enumerate(entries)
        if (entry.country_code or "").lower() == code
    }
    if not removed_days:
        raise ValueError("No days found for that country.")
    if len(removed_days) >= len(entries):
        raise ValueError("Cannot remove every day from the trip.")

    remaining = [entry for index, entry in enumerate(entries) if index + 1 not in removed_days]
    _delete_activities_on_days(db, trip, removed_days)

    mapping: dict[int, int] = {}
    new_day = 1
    for old_day in range(1, len(entries) + 1):
        if old_day in removed_days:
            continue
        mapping[old_day] = new_day
        new_day += 1
    _remap_activity_days(trip, mapping)
    persist_day_plan(trip, remaining)


def delete_city(db: Session, trip: Trip, country_code: str, city_name: str) -> None:
    code = (country_code or "").strip().lower()
    city = (city_name or "").strip()
    if not code or not city:
        raise ValueError("Unknown city.")

    entries = day_plan_entries(trip)
    removed_days: set[int] = set()
    for index, entry in enumerate(entries):
        if (entry.country_code or "").lower() != code:
            continue
        short_name = shorten_city_name(entry.full_name, entry.country_code)
        if short_name == city or entry.full_name == city:
            removed_days.add(index + 1)

    if not removed_days:
        raise ValueError("No days found for that city.")
    if len(removed_days) >= len(entries):
        raise ValueError("Cannot remove every day from the trip.")

    remaining = [entry for index, entry in enumerate(entries) if index + 1 not in removed_days]
    _delete_activities_on_days(db, trip, removed_days)

    mapping: dict[int, int] = {}
    new_day = 1
    for old_day in range(1, len(entries) + 1):
        if old_day in removed_days:
            continue
        mapping[old_day] = new_day
        new_day += 1
    _remap_activity_days(trip, mapping)
    persist_day_plan(trip, remaining)


def country_codes_on_trip(trip: Trip) -> list[dict]:
    codes: list[dict] = []
    seen: set[str | None] = set()
    for entry in day_plan_entries(trip):
        key = entry.country_code
        if key in seen:
            continue
        seen.add(key)
        codes.append({"code": key, "name": country_label(key)})
    return codes
