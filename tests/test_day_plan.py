"""Tests for location formatting and day-plan maintenance."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DATABASE_PATH"] = str(Path(tempfile.gettempdir()) / "group_day_planner_day_plan_test.db")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Activity, Member, Trip, TripDestination, share_code as make_share_code
from app.services.day_plan import delete_day, reorder_days, trim_activities_beyond_num_days
from app.services.destinations import backfill_location_summary, format_location_summary_by_country
from app.services.members import get_or_create_trip_member
from app.services.route_plan import sync_trip_from_route_plan


class LocationSummaryTests(unittest.TestCase):
    def test_single_city_with_multiple_rows_uses_plain_city(self):
        pairs = [("London", "gb"), ("London", "gb"), ("London", "gb")]
        self.assertEqual(format_location_summary_by_country(pairs), "London")

    def test_same_country_dedupes_repeated_cities(self):
        pairs = [("London", "gb"), ("London", "gb"), ("Oxford", "gb")]
        self.assertEqual(format_location_summary_by_country(pairs), "United Kingdom: London, Oxford")

    def test_backfill_location_summary_fixes_legacy_string(self):
        trip = Trip(name="T", date="2026-01-01", location="United Kingdom: London, London, London", share_code="abc")
        trip.destinations = [
            TripDestination(name="London", country_code="gb", sort_order=0, start_day=1),
            TripDestination(name="London", country_code="gb", sort_order=1, start_day=2),
            TripDestination(name="London", country_code="gb", sort_order=2, start_day=3),
        ]
        self.assertTrue(backfill_location_summary(trip))
        self.assertEqual(trip.location, "London")


class DayPlanTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()
        self.trip = Trip(
            name="Trip",
            date="2026-07-01",
            location="London",
            share_code=make_share_code(),
            num_days=3,
        )
        self.db.add(self.trip)
        self.db.flush()
        self.member = Member(trip_id=self.trip.id, display_name="Host", is_creator=True)
        self.db.add(self.member)
        self.db.flush()
        for day in (1, 2, 3):
            self.db.add(
                Activity(
                    trip_id=self.trip.id,
                    day_number=day,
                    title=f"Day {day}",
                    proposed_by_id=self.member.id,
                )
            )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_trim_activities_beyond_num_days(self):
        removed = trim_activities_beyond_num_days(self.db, self.trip, 1)
        self.db.commit()
        self.assertEqual(removed, 2)
        remaining = self.db.query(Activity).filter(Activity.trip_id == self.trip.id).all()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].day_number, 1)

    def test_delete_day_removes_activities_and_remaps(self):
        self.trip.destinations = [
            TripDestination(name="London", country_code="gb", sort_order=0, start_day=1),
            TripDestination(name="London", country_code="gb", sort_order=1, start_day=2),
            TripDestination(name="London", country_code="gb", sort_order=2, start_day=3),
        ]
        self.db.commit()
        delete_day(self.db, self.trip, 2)
        self.db.commit()
        days = sorted(a.day_number for a in self.trip.activities)
        self.assertEqual(days, [1, 2])
        self.assertEqual(self.trip.num_days, 2)

    def test_reorder_days_remaps_activities(self):
        self.trip.destinations = [
            TripDestination(name="A", country_code="gb", sort_order=0, start_day=1),
            TripDestination(name="B", country_code="gb", sort_order=1, start_day=2),
        ]
        self.trip.num_days = 2
        self.db.commit()
        reorder_days(self.trip, [2, 1])
        by_day = {a.day_number: a.title for a in self.trip.activities}
        self.assertEqual(by_day[1], "Day 2")
        self.assertEqual(by_day[2], "Day 1")


class EditTripShorteningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.database import init_db
        from app.main import app

        init_db()
        cls.client = TestClient(app)

    def _csrf_headers(self):
        token = self.client.cookies.get("gdp_csrf")
        return {"X-CSRF-Token": token} if token else {}

    def test_edit_route_plan_shortening_deletes_extra_day_activities(self):
        from app.database import SessionLocal

        db = SessionLocal()
        code = make_share_code()
        trip = Trip(name="Route", date="2026-07-01", location="", share_code=code, num_days=3)
        db.add(trip)
        db.flush()
        host = Member(trip_id=trip.id, display_name="Host", is_creator=True)
        db.add(host)
        db.flush()
        sync_trip_from_route_plan(
            trip,
            {
                "countries": [
                    {
                        "name": "United Kingdom",
                        "code": "gb",
                        "cities": [{"name": "London", "days": 3}],
                    }
                ]
            },
        )
        for day in (1, 2, 3):
            db.add(
                Activity(
                    trip_id=trip.id,
                    day_number=day,
                    title=f"Act {day}",
                    proposed_by_id=host.id,
                )
            )
        db.commit()
        host_id = host.id
        trip_id = trip.id
        db.close()

        self.client.get("/")
        self.client.cookies.set(f"gdp_member_{code}", host_id)
        res = self.client.post(
            f"/t/{code}/edit",
            data={
                "name": "Route",
                "date": "2026-07-01",
                "route_plan": '{"countries":[{"name":"United Kingdom","code":"gb","cities":[{"name":"London","days":1}]}]}',
                "num_days": "1",
            },
            headers=self._csrf_headers(),
            follow_redirects=False,
        )
        self.assertEqual(res.status_code, 303)

        db = SessionLocal()
        activities = db.query(Activity).filter(Activity.trip_id == trip_id).all()
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0].day_number, 1)
        trip = db.query(Trip).filter(Trip.id == trip_id).first()
        self.assertEqual(trip.num_days, 1)
        db.delete(trip)
        db.commit()
        db.close()


class JoinDedupTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()
        self.trip = Trip(name="T", date="2026-07-01", location="London", share_code=make_share_code(), num_days=1)
        self.db.add(self.trip)
        self.db.flush()
        self.existing = Member(trip_id=self.trip.id, display_name="Jordan", joined_at=datetime.utcnow())
        self.db.add(self.existing)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_get_or_create_reuses_existing_member_by_name(self):
        member, created = get_or_create_trip_member(self.db, self.trip, "Jordan")
        self.assertFalse(created)
        self.assertEqual(member.id, self.existing.id)

    def test_get_or_create_reuses_cookie_member(self):
        member, created = get_or_create_trip_member(
            self.db,
            self.trip,
            "Someone else",
            cookie_member_id=self.existing.id,
        )
        self.assertFalse(created)
        self.assertEqual(member.id, self.existing.id)
