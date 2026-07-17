"""Smoke tests for key pages — catch 500s on common user flows."""

import unittest

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.models import Member, Trip, TripDestination, share_code as make_share_code


class SmokeTests(unittest.TestCase):
    share_code: str
    member_id: str

    @classmethod
    def setUpClass(cls):
        init_db()
        db = SessionLocal()
        cls.share_code = make_share_code()
        trip = Trip(
            name="London trip",
            date="2026-07-17",
            location="United Kingdom: London",
            share_code=cls.share_code,
            num_days=5,
        )
        db.add(trip)
        db.flush()
        member = Member(trip_id=trip.id, display_name="Sylvie", is_creator=True)
        db.add(member)
        db.add(
            TripDestination(
                trip_id=trip.id,
                name="London Apprentice",
                country_code="gb",
                sort_order=0,
                start_day=1,
            )
        )
        db.commit()
        cls.member_id = member.id
        db.close()

    @classmethod
    def tearDownClass(cls):
        db = SessionLocal()
        trip = db.query(Trip).filter(Trip.share_code == cls.share_code).first()
        if trip:
            db.query(Member).filter(Member.trip_id == trip.id).delete()
            db.query(TripDestination).filter(TripDestination.trip_id == trip.id).delete()
            db.delete(trip)
            db.commit()
        db.close()

    def setUp(self):
        from app.main import app

        self.client = TestClient(app)
        self.client.get("/")
        self.client.cookies.set(f"gdp_member_{self.share_code}", self.member_id)

    def test_homepage_loads(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Where to next?", res.content)

    def test_trip_board_loads(self):
        res = self.client.get(f"/t/{self.share_code}")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"London trip", res.content)

    def test_edit_trip_page_loads(self):
        res = self.client.get(f"/t/{self.share_code}/edit")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Edit trip details", res.content)

    def test_join_page_loads(self):
        self.client.cookies.clear()
        res = self.client.get(f"/t/{self.share_code}/join")
        self.assertEqual(res.status_code, 200)

    def test_trip_exists_api(self):
        res = self.client.get(f"/t/{self.share_code}/exists")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["exists"])
