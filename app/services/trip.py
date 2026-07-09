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
        activities.append(enriched)
        activity_map[activity.id] = enriched

    grouped = {
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
        grouped=grouped,
        itinerary=itinerary,
        is_creator=is_creator,
    )
