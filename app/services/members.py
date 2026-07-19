"""Shared member lookup and removal logic."""

from sqlalchemy.orm import Session

from app.models import Activity, Member, User, UserTrip


class OnlyTravelerError(ValueError):
    """Raised when removing the last member from a trip."""


def get_or_create_trip_member(
    db: Session,
    trip,
    display_name: str,
    *,
    user: User | None = None,
    cookie_member_id: str | None = None,
) -> tuple[Member, bool]:
    """
    Resolve an existing member for join, or create a new one.
    Returns (member, created).
    """
    if cookie_member_id:
        existing = (
            db.query(Member)
            .filter(Member.id == cookie_member_id, Member.trip_id == trip.id)
            .first()
        )
        if existing:
            return existing, False

    if user:
        for member in db.query(Member).filter(Member.trip_id == trip.id).all():
            if member.display_name.strip().lower() == user.display_name.strip().lower():
                return member, False
        linked = find_or_create_member_for_user(db, trip, user)
        if linked:
            return linked, False

    normalized = display_name.strip().lower()
    if normalized:
        for member in db.query(Member).filter(Member.trip_id == trip.id).all():
            if member.display_name.strip().lower() == normalized:
                return member, False

    member = Member(trip_id=trip.id, display_name=display_name.strip())
    db.add(member)
    return member, True


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


def next_trip_host(db: Session, trip_id: str, *, exclude_member_id: str) -> Member | None:
    """Return the member who joined earliest, excluding one member."""
    return (
        db.query(Member)
        .filter(Member.trip_id == trip_id, Member.id != exclude_member_id)
        .order_by(Member.joined_at.asc(), Member.id.asc())
        .first()
    )


def transfer_trip_host(db: Session, trip_id: str, from_member: Member, to_member: Member) -> None:
    """Move host privileges from one member to another."""
    from_member.is_creator = False
    to_member.is_creator = True

    links = db.query(UserTrip).filter(UserTrip.trip_id == trip_id).all()
    for link in links:
        link.is_creator = False

    normalized = to_member.display_name.strip().lower()
    if normalized:
        for link in links:
            user = link.user
            if user and user.display_name.strip().lower() == normalized:
                link.is_creator = True
                break


def reassign_and_remove_member(db: Session, trip_id: str, target: Member) -> Member | None:
    """
    Remove a member from a trip, reassigning their activities.
    If the target is the host, pass hosting to the member who joined earliest.
    Returns the new host when hosting was transferred, else None.
    """
    successor: Member | None = None
    activity_owner: Member | None = None

    if target.is_creator:
        successor = next_trip_host(db, trip_id, exclude_member_id=target.id)
        if not successor:
            raise OnlyTravelerError("You're the only traveler on this trip.")
        transfer_trip_host(db, trip_id, target, successor)
        activity_owner = successor
    else:
        activity_owner = (
            db.query(Member)
            .filter(Member.trip_id == trip_id, Member.is_creator.is_(True))
            .first()
        )

    if activity_owner and activity_owner.id != target.id:
        (
            db.query(Activity)
            .filter(Activity.trip_id == trip_id, Activity.proposed_by_id == target.id)
            .update({Activity.proposed_by_id: activity_owner.id}, synchronize_session=False)
        )

    db.delete(target)
    return successor
