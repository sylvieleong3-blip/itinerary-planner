"""Tests for security helpers and member validation."""

import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI, Form
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.middleware import csrf_middleware
from app.models import Member, Trip, User, UserTrip, Vote, share_code as make_share_code
from app.services.photos import save_trip_photo
from app.services.security import get_secret_key, rate_limit


class SecurityHelpersTests(unittest.TestCase):
    def test_share_code_length(self):
        code = make_share_code()
        self.assertEqual(len(code), 10)

    def test_rate_limit_blocks_after_max(self):
        key = "test-ip"
        self.assertTrue(rate_limit(key, max_calls=2, window_sec=60))
        self.assertTrue(rate_limit(key, max_calls=2, window_sec=60))
        self.assertFalse(rate_limit(key, max_calls=2, window_sec=60))

    def test_production_requires_secret_key(self):
        env = os.environ.copy()
        env["RENDER"] = "true"
        env.pop("SECRET_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            with patch("app.services.security._secret_key", None):
                with self.assertRaises(RuntimeError):
                    get_secret_key()

    def test_save_trip_photo_rejects_bad_magic_bytes(self):
        with self.assertRaises(ValueError):
            save_trip_photo("trip1", b"not-an-image", "image/jpeg")

    def test_save_trip_photo_accepts_jpeg(self):
        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20
        path = save_trip_photo("trip-test", jpeg, "image/jpeg")
        self.assertTrue(path.endswith(".jpg"))


class MemberValidationTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()
        self.trip = Trip(
            name="Test",
            date="2026-07-15",
            location="London",
            share_code="abc1234567",
            num_days=2,
        )
        self.db.add(self.trip)
        self.db.commit()
        self.member = Member(trip_id=self.trip.id, display_name="Sylvie", is_creator=True)
        self.db.add(self.member)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_get_trip_member_accepts_valid_member(self):
        from app.dependencies import get_trip_member

        trip, member = get_trip_member(self.db, self.trip.share_code, self.member.id)
        self.assertIsNotNone(trip)
        self.assertEqual(member.id, self.member.id)

    def test_get_trip_member_rejects_cross_trip_cookie(self):
        from app.dependencies import get_trip_member

        other_trip = Trip(
            name="Other",
            date="2026-07-16",
            location="Paris",
            share_code="xyz9876543",
            num_days=1,
        )
        self.db.add(other_trip)
        self.db.commit()
        other_member = Member(trip_id=other_trip.id, display_name="Other", is_creator=True)
        self.db.add(other_member)
        self.db.commit()

        trip, member = get_trip_member(self.db, self.trip.share_code, other_member.id)
        self.assertIsNotNone(trip)
        self.assertIsNone(member)


class LoggedInMemberRestoreTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db = Session()
        self.trip = Trip(
            name="Corsica",
            date="2026-07-15",
            location="Corsica",
            share_code="gpmiof0m2v",
            num_days=5,
        )
        self.db.add(self.trip)
        self.db.commit()
        self.member = Member(trip_id=self.trip.id, display_name="Luna", is_creator=True)
        self.db.add(self.member)
        self.user = User(
            email="luna@example.com",
            display_name="Luna",
            password_hash="x",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.add(
            UserTrip(user_id=self.user.id, trip_id=self.trip.id, is_creator=True)
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_find_member_matches_creator_by_user_trip(self):
        from app.services.members import find_or_create_member_for_user

        member = find_or_create_member_for_user(self.db, self.trip, self.user)
        self.assertEqual(member.id, self.member.id)

    def test_require_trip_member_redirect_restores_logged_in_user(self):
        from starlette.requests import Request

        from app.dependencies import require_trip_member_redirect

        scope = {
            "type": "http",
            "method": "GET",
            "path": f"/t/{self.trip.share_code}",
            "headers": [],
            "query_string": b"",
        }
        request = Request(scope)

        with patch("app.dependencies.get_user_from_request", return_value=self.user):
            auth = require_trip_member_redirect(request, self.trip.share_code, self.db)

        self.assertNotIsInstance(auth, RedirectResponse)
        trip, member = auth
        self.assertEqual(trip.id, self.trip.id)
        self.assertEqual(member.id, self.member.id)
        self.assertEqual(
            request.state.pending_member_cookie,
            (self.trip.share_code, self.member.id),
        )


class CsrfMiddlewareTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.middleware("http")(csrf_middleware)

        @app.get("/")
        def home():
            return {"ok": True}

        @app.post("/echo")
        def echo():
            return {"ok": True}

        @app.post("/form-echo")
        async def form_echo(name: str = Form(...)):
            return {"name": name}

        self.client = TestClient(app)

    def test_post_without_csrf_is_rejected(self):
        res = self.client.post("/echo", json={"hello": "world"})
        self.assertEqual(res.status_code, 403)

    def test_post_with_matching_csrf_succeeds(self):
        self.client.get("/")
        token = self.client.cookies.get("gdp_csrf")
        self.assertTrue(token)
        res = self.client.post("/echo", headers={"X-CSRF-Token": token}, json={"hello": "world"})
        self.assertEqual(res.status_code, 200)

    def test_form_post_with_hidden_csrf_succeeds(self):
        self.client.get("/")
        token = self.client.cookies.get("gdp_csrf")
        res = self.client.post(
            "/form-echo",
            data={"name": "London", "csrf_token": token},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["name"], "London")


class VotingLockTests(unittest.TestCase):
    def setUp(self):
        from app.database import SessionLocal, init_db
        from app.models import Activity

        init_db()
        self.db = SessionLocal()
        self.share_code = make_share_code()
        self.trip = Trip(
            name="Vote Test",
            date="2026-07-15",
            location="Paris",
            share_code=self.share_code,
            num_days=2,
            voting_enabled=True,
            voting_locked=True,
        )
        self.db.add(self.trip)
        self.db.commit()
        self.member = Member(trip_id=self.trip.id, display_name="Host", is_creator=True)
        self.db.add(self.member)
        self.db.commit()
        self.activity = Activity(
            trip_id=self.trip.id,
            title="Museum",
            is_suggested=True,
            day_number=1,
            proposed_by_id=self.member.id,
        )
        self.db.add(self.activity)
        self.db.commit()

    def tearDown(self):
        from app.models import Activity

        self.db.query(Vote).filter(Vote.activity_id == self.activity.id).delete()
        self.db.query(Activity).filter(Activity.trip_id == self.trip.id).delete()
        self.db.query(Member).filter(Member.trip_id == self.trip.id).delete()
        self.db.query(Trip).filter(Trip.id == self.trip.id).delete()
        self.db.commit()
        self.db.close()

    def test_vote_blocked_when_locked(self):
        from app.main import app

        client = TestClient(app)
        client.get("/")
        token = client.cookies.get("gdp_csrf")
        client.cookies.set(f"gdp_member_{self.share_code}", self.member.id)
        res = client.post(
            f"/t/{self.share_code}/vote/{self.activity.id}",
            data={"rating": "5", "csrf_token": token},
            follow_redirects=False,
        )
        self.assertEqual(res.status_code, 303)
        self.assertIn("error=voting_locked", res.headers.get("location", ""))


class WeatherResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_trip_weather_survives_network_error(self):
        from unittest.mock import AsyncMock, patch

        from app.services.weather import fetch_trip_weather

        with patch("app.services.weather._resolve_coords", AsyncMock(side_effect=Exception("network down"))):
            result = await fetch_trip_weather("Paris", "2026-07-15", 3)
        self.assertEqual(result, {})


class DestinationNameTests(unittest.TestCase):
    def test_canonical_destination_name_fixes_corscia(self):
        from app.services.destinations import canonical_destination_name

        self.assertEqual(canonical_destination_name("Corscia"), "Corsica")
        self.assertEqual(canonical_destination_name("Corscia, France"), "Corsica, France")


class TursoConfigTests(unittest.TestCase):
    def test_placeholder_env_vars_do_not_enable_turso(self):
        from app.database import _turso_configured

        with patch.dict(
            os.environ,
            {
                "TURSO_DATABASE_URL": "libsql://your-database-name-org.turso.io",
                "TURSO_AUTH_TOKEN": "your-auth-token",
            },
            clear=False,
        ):
            self.assertFalse(_turso_configured())

    def test_realistic_turso_env_vars_enable_turso(self):
        from app.database import _turso_configured

        with patch.dict(
            os.environ,
            {
                "TURSO_DATABASE_URL": "libsql://group-day-planner-user.turso.io",
                "TURSO_AUTH_TOKEN": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example",
            },
            clear=False,
        ):
            self.assertTrue(_turso_configured())


if __name__ == "__main__":
    unittest.main()