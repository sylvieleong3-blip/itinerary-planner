"""Shared member lookup and removal logic."""

from sqlalchemy.orm import Session

from app.models import Activity, Member, User, UserTrip


def find_or_create_member_for_user(db: Session, trip, user: User) -> Member | None:
    """Resolve a trip member for a logged-in user linked via UserTrip."""
    link = (
        db.query(UserTrip)
        .filter(UserTrip.user_id == user.id, UserTrip.trip_id == trip.id)
        .first()
    )
    if not link:
        return None

    if link.is_creator:
        creator = (
            db.query(Member)
            .filter(Member.trip_id == trip.id, Member.is_creator.is_(True))
            .first()
        )
        if creator:
            return creator

    normalized = user.display_name.strip().lower()
    if normalized:
        for member in db.query(Member).filter(Member.trip_id == trip.id).all():
            if member.display_name.strip().lower() == normalized:
                return member

    member = Member(
        trip_id=trip.id,
        display_name=user.display_name.strip() or "Traveler",
        is_creator=link.is_creator,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def reassign_and_remove_member(db: Session, trip_id: str, target: Member) -> None:
    creator = (
        db.query(Member)
        .filter(Member.trip_id == trip_id, Member.is_creator.is_(True))
        .first()
    )
    if creator and creator.id != target.id:
        (
            db.query(Activity)
            .filter(Activity.trip_id == trip_id, Activity.proposed_by_id == target.id)
            .update({Activity.proposed_by_id: creator.id}, synchronize_session=False)
        )

    db.delete(target)
