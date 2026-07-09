from dataclasses import dataclass

from sqlalchemy.orm import Session, joinedload

from app.models import Activity, ItineraryItem, Trip, Vote
from app.services.distance import (
    Coordinates,
    DistanceResult,
    format_distance,
    format_travel_time,
    haversine_distance,
    has_coordinates,
)
from app.services.dates import format_day_date
from app.services.scoring import VoteSummary, compute_vote_summary


@dataclass
class EnrichedActivity:
    activity: Activity
    summary: VoteSummary
    my_vote: int | None
    my_veto_reason: str | None


@dataclass
class ItineraryStop:
    item: ItineraryItem
    activity: EnrichedActivity
    distance_from_previous: DistanceResult | None
    distance_formatted: str | None
    travel_time: str | None


@dataclass
class EnrichedTrip:
    trip: Trip
    activities: list[EnrichedActivity]
    suggested: list[EnrichedActivity]
    grouped: dict[str, list[EnrichedActivity]]
    itinerary: list[ItineraryStop]
    is_creator: bool


def get_trip_by_code(db: Session, share_code: str) -> Trip | None:
    return (
        db.query(Trip)
        .options(
            joinedload(Trip.members),
            joinedload(Trip.activities).joinedload(Activity.proposed_by),
            joinedload(Trip.activities).joinedload(Activity.votes).joinedload(Vote.member),
            joinedload(Trip.itinerary_items).joinedload(ItineraryItem.activity),
        )
        .filter(Trip.share_code == share_code)
        .first()
    )


def enrich_trip(trip: Trip, member_id: str | None = None) -> EnrichedTrip:
    total_members = len(trip.members) or 1

    activities: list[EnrichedActivity] = []
    suggested: list[EnrichedActivity] = []
    activity_map: dict[str, EnrichedActivity] = {}

    for activity in sorted(trip.activities, key=lambda a: a.created_at):
        ratings = [
            (v.rating, v.member.display_name, v.veto_reason)
            for v in activity.votes
        ]
        summary = compute_vote_summary(ratings, total_members)
        my_vote = None
        my_veto_reason = None
        if member_id:
            for v in activity.votes:
                if v.member_id == member_id:
                    my_vote = v.rating
                    my_veto_reason = v.veto_reason
                    break

        enriched = EnrichedActivity(
            activity=activity,
            summary=summary,
            my_vote=my_vote,
            my_veto_reason=my_veto_reason,
        )
        if activity.is_suggested:
            suggested.append(enriched)
        else:
            activities.append(enriched)
        activity_map[activity.id] = enriched

    grouped = {
        "activities": activities,
        "likely": [a for a in activities if a.summary.status == "likely"],
        "maybe": [a for a in activities if a.summary.status == "maybe"],
        "vetoed": [a for a in activities if a.summary.status == "vetoed"],
        "unlikely": [a for a in activities if a.summary.status == "unlikely"],
        "unrated": [a for a in activities if a.summary.status == "unrated"],
    }

    itinerary: list[ItineraryStop] = []
    sorted_items = sorted(trip.itinerary_items, key=lambda i: i.order)

    for index, item in enumerate(sorted_items):
        prev_activity = sorted_items[index - 1].activity if index > 0 else None
        curr = item.activity

        distance_result = None
        distance_formatted = None
        travel_time = None

        if (
            prev_activity
            and has_coordinates(prev_activity.latitude, prev_activity.longitude)
            and has_coordinates(curr.latitude, curr.longitude)
        ):
            distance_result = haversine_distance(
                Coordinates(prev_activity.latitude, prev_activity.longitude),
                Coordinates(curr.latitude, curr.longitude),
            )
            distance_formatted = format_distance(distance_result)
            travel_time = format_travel_time(distance_result)

        enriched_activity = activity_map.get(item.activity_id)
        if not enriched_activity:
            ratings = [(v.rating, v.member.display_name, v.veto_reason) for v in curr.votes]
            enriched_activity = EnrichedActivity(
                activity=curr,
                summary=compute_vote_summary(ratings, total_members),
                my_vote=None,
                my_veto_reason=None,
            )

        itinerary.append(
            ItineraryStop(
                item=item,
                activity=enriched_activity,
                distance_from_previous=distance_result,
                distance_formatted=distance_formatted,
                travel_time=travel_time,
            )
        )

    is_creator = False
    if member_id:
        is_creator = any(m.id == member_id and m.is_creator for m in trip.members)

    return EnrichedTrip(
        trip=trip,
        activities=activities,
        suggested=suggested,
        grouped=grouped,
        itinerary=itinerary,
        is_creator=is_creator,
    )


def build_day_board(
    enriched: EnrichedTrip,
    sections: list[tuple[str, str]],
) -> list[dict]:
    num_days = enriched.trip.num_days or 1
    days: list[dict] = []
    for day in range(1, num_days + 1):
        day_sections = []
        day_suggested = [
            a for a in enriched.suggested
            if (a.activity.day_number or 1) == day
        ]
        for key, title in sections:
            items = [
                a for a in enriched.grouped[key]
                if (a.activity.day_number or 1) == day
            ]
            if items:
                day_sections.append({"key": key, "title": title, "items": items})
        if day_suggested:
            day_sections.append({
                "key": "suggested",
                "title": "Suggested",
                "items": day_suggested,
            })
        days.append({
            "day": day,
            "date_label": format_day_date(enriched.trip.date, day),
            "sections": day_sections,
        })
    return days


def build_builder_days(
    trip: Trip,
    builder_items: list[dict],
    pool: list,
) -> list[dict] | None:
    num_days = trip.num_days or 1
    if num_days <= 1:
        return None

    days: list[dict] = []
    for day in range(1, num_days + 1):
        day_items = [
            item for item in builder_items
            if (item["activity"].activity.day_number or 1) == day
        ]
        day_pool = [
            act for act in pool
            if (act.activity.day_number or 1) == day
        ]
        days.append({
            "day": day,
            "date_label": format_day_date(trip.date, day),
            "builder_items": day_items,
            "pool": day_pool,
        })
    return days


def group_itinerary_by_day(itinerary: list[ItineraryStop], start_date: str) -> list[dict]:
    if not itinerary:
        return []

    days_map: dict[int, list[ItineraryStop]] = {}
    for stop in itinerary:
        day = stop.activity.activity.day_number or 1
        days_map.setdefault(day, []).append(stop)

    return [
        {
            "day": day,
            "date_label": format_day_date(start_date, day),
            "stops": days_map[day],
        }
        for day in sorted(days_map)
    ]
