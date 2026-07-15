import secrets
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def share_code() -> str:
    return "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(6))


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    trips: Mapped[list["UserTrip"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserTrip(Base):
    __tablename__ = "user_trips"
    __table_args__ = (UniqueConstraint("user_id", "trip_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"))
    trip_id: Mapped[str] = mapped_column(String, ForeignKey("trips.id", ondelete="CASCADE"))
    is_creator: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="trips")
    trip: Mapped["Trip"] = relationship()


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String)
    date: Mapped[str] = mapped_column(String)
    location: Mapped[str] = mapped_column(String)
    share_code: Mapped[str] = mapped_column(String, unique=True, index=True)
    start_time: Mapped[str | None] = mapped_column(String, nullable=True)
    end_time: Mapped[str | None] = mapped_column(String, nullable=True)
    num_days: Mapped[int] = mapped_column(Integer, default=1)
    voting_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    members: Mapped[list["Member"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    activities: Mapped[list["Activity"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    itinerary_items: Mapped[list["ItineraryItem"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="ItineraryItem.order"
    )


class Member(Base):
    __tablename__ = "members"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(String, ForeignKey("trips.id", ondelete="CASCADE"))
    display_name: Mapped[str] = mapped_column(String)
    is_creator: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    trip: Mapped["Trip"] = relationship(back_populates="members")
    votes: Mapped[list["Vote"]] = relationship(back_populates="member", cascade="all, delete-orphan")
    activities: Mapped[list["Activity"]] = relationship(back_populates="proposed_by")


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(String, ForeignKey("trips.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    suggested_time: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_min: Mapped[int] = mapped_column(Integer, default=60)
    day_number: Mapped[int] = mapped_column(Integer, default=1)
    category: Mapped[str] = mapped_column(String, default="activity")
    is_suggested: Mapped[bool] = mapped_column(Boolean, default=False)
    photo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String, nullable=True)
    proposed_by_id: Mapped[str] = mapped_column(String, ForeignKey("members.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    trip: Mapped["Trip"] = relationship(back_populates="activities")
    proposed_by: Mapped["Member"] = relationship(back_populates="activities")
    votes: Mapped[list["Vote"]] = relationship(back_populates="activity", cascade="all, delete-orphan")
    itinerary_item: Mapped["ItineraryItem | None"] = relationship(back_populates="activity", uselist=False)


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("activity_id", "member_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    activity_id: Mapped[str] = mapped_column(String, ForeignKey("activities.id", ondelete="CASCADE"))
    member_id: Mapped[str] = mapped_column(String, ForeignKey("members.id", ondelete="CASCADE"))
    rating: Mapped[int] = mapped_column(Integer)
    veto_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    activity: Mapped["Activity"] = relationship(back_populates="votes")
    member: Mapped["Member"] = relationship(back_populates="votes")


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(String, ForeignKey("trips.id", ondelete="CASCADE"))
    activity_id: Mapped[str] = mapped_column(String, ForeignKey("activities.id", ondelete="CASCADE"), unique=True)
    order: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[str] = mapped_column(String)
    duration_min: Mapped[int] = mapped_column(Integer, default=60)
    override_note: Mapped[str | None] = mapped_column(String, nullable=True)

    trip: Mapped["Trip"] = relationship(back_populates="itinerary_items")
    activity: Mapped["Activity"] = relationship(back_populates="itinerary_item")
