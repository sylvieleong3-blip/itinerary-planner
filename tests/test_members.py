"""Tests for member removal and host transfer."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DATABASE_PATH"] = str(Path(tempfile.gettempdir()) / "group_day_planner_members_test.db")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Activity, Member, Trip, share_code as make_share_code
from app.services.members import OnlyTravelerError, next_trip_host, reassign_and_remove_member


class MemberServiceTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()
        self.trip = Trip(
            name="Test",
            date="2026-07-15",
            location="London",
            share_code=make_share_code(),
            num_days=2,
        )
        self.db.add(self.trip)
        self.db.flush()

        now = datetime.utcnow()
        self.host = Member(
            trip_id=self.trip.id,
            display_name="Host",
            is_creator=True,
            joined_at=now,
        )
        self.early = Member(
            trip_id=self.trip.id,
            display_name="Early",
            joined_at=now + timedelta(hours=1),
        )
        self.late = Member(
            trip_id=self.trip.id,
            display_name="Late",
            joined_at=now + timedelta(hours=2),
        )
        self.db.add_all([self.host, self.early, self.late])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_next_trip_host_returns_earliest_other_member(self):
        successor = next_trip_host(self.db, self.trip.id, exclude_member_id=self.host.id)
        self.assertEqual(successor.id, self.early.id)

    def test_host_leave_transfers_to_earliest_member(self):
        successor = reassign_and_remove_member(self.db, self.trip.id, self.host)
        self.db.commit()
        self.assertEqual(successor.id, self.early.id)
        self.assertIsNone(self.db.get(Member, self.host.id))
        new_host = self.db.get(Member, self.early.id)
        self.assertTrue(new_host.is_creator)

    def test_only_traveler_cannot_leave(self):
        reassign_and_remove_member(self.db, self.trip.id, self.early)
        reassign_and_remove_member(self.db, self.trip.id, self.late)
        self.db.commit()
        with self.assertRaises(OnlyTravelerError):
            reassign_and_remove_member(self.db, self.trip.id, self.host)

    def test_removed_member_activities_reassigned_to_host(self):
        activity = Activity(
            trip_id=self.trip.id,
            day_number=1,
            title="Museum",
            proposed_by_id=self.late.id,
            is_suggested=True,
        )
        self.db.add(activity)
        self.db.commit()

        reassign_and_remove_member(self.db, self.trip.id, self.late)
        self.db.commit()

        self.db.refresh(activity)
        self.assertEqual(activity.proposed_by_id, self.host.id)


class MemberRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.database import init_db
        from app.main import app

        init_db()
        cls.client = TestClient(app)

    def _make_trip(self):
        from app.database import SessionLocal

        db = SessionLocal()
        code = make_share_code()
        trip = Trip(name="Route test", date="2026-07-15", location="London", share_code=code, num_days=2)
        db.add(trip)
        db.flush()
        now = datetime.utcnow()
        host = Member(trip_id=trip.id, display_name="Host", is_creator=True, joined_at=now)
        guest = Member(
            trip_id=trip.id,
            display_name="Guest",
            joined_at=now + timedelta(hours=1),
        )
        db.add_all([host, guest])
        db.commit()
        ids = (code, host.id, guest.id, trip.id)
        db.close()
        return ids

    def _csrf_headers(self):
        token = self.client.cookies.get("gdp_csrf")
        return {"X-CSRF-Token": token} if token else {}

    def test_host_can_remove_guest(self):
        code, host_id, guest_id, trip_id = self._make_trip()
        self.client.get("/")
        self.client.cookies.set(f"gdp_member_{code}", host_id)
        res = self.client.post(
            f"/t/{code}/members/{guest_id}/remove",
            headers=self._csrf_headers(),
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])

        from app.database import SessionLocal

        db = SessionLocal()
        self.assertIsNone(db.query(Member).filter(Member.id == guest_id).first())
        db.delete(db.query(Trip).filter(Trip.id == trip_id).first())
        db.commit()
        db.close()

    def test_host_leave_transfers_hosting(self):
        code, host_id, guest_id, trip_id = self._make_trip()
        self.client.get("/")
        self.client.cookies.set(f"gdp_member_{code}", host_id)
        res = self.client.post(
            f"/t/{code}/leave",
            follow_redirects=False,
            headers=self._csrf_headers(),
        )
        self.assertEqual(res.status_code, 303)

        from app.database import SessionLocal

        db = SessionLocal()
        self.assertIsNone(db.query(Member).filter(Member.id == host_id).first())
        guest = db.query(Member).filter(Member.id == guest_id).first()
        self.assertTrue(guest.is_creator)
        db.delete(db.query(Trip).filter(Trip.id == trip_id).first())
        db.commit()
        db.close()
