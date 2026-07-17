"""Tests for backpack route plan day assignment."""

import unittest

from app.models import Trip, TripDestination
from app.services.route_plan import (
    compute_start_days,
    flatten_route_plan,
    parse_route_plan,
    route_plan_timeline,
    sync_trip_from_route_plan,
    trip_to_route_plan,
)


class RoutePlanDayAssignmentTests(unittest.TestCase):
    def test_compute_start_days(self):
        self.assertEqual(compute_start_days([2, 1, 3]), [1, 3, 4])
        self.assertEqual(compute_start_days([5]), [1])
        self.assertEqual(compute_start_days([1, 1, 1]), [1, 2, 3])

    def test_malaysia_thailand_example(self):
        plan = parse_route_plan(
            {
                "countries": [
                    {
                        "name": "Malaysia",
                        "code": "my",
                        "cities": [
                            {"name": "Kuala Lumpur", "days": 2},
                            {"name": "Malacca", "days": 1},
                        ],
                    },
                    {
                        "name": "Thailand",
                        "code": "th",
                        "cities": [{"name": "Bangkok", "days": 3}],
                    },
                ]
            }
        )
        flat = flatten_route_plan(plan)
        self.assertEqual(
            flat,
            [
                ("Kuala Lumpur", "my", 2, 1),
                ("Malacca", "my", 1, 3),
                ("Bangkok", "th", 3, 4),
            ],
        )
        timeline = route_plan_timeline(plan)
        self.assertEqual(timeline[0]["start_day"], 1)
        self.assertEqual(timeline[0]["end_day"], 2)
        self.assertEqual(timeline[1]["start_day"], 3)
        self.assertEqual(timeline[2]["start_day"], 4)
        self.assertEqual(timeline[2]["end_day"], 6)

    def test_sync_trip_from_route_plan(self):
        trip = Trip(name="Test", date="2026-01-01", location="", share_code="abc123")
        total = sync_trip_from_route_plan(
            trip,
            {
                "countries": [
                    {
                        "name": "Malaysia",
                        "code": "my",
                        "cities": [
                            {"name": "Kuala Lumpur", "days": 2},
                            {"name": "Malacca", "days": 1},
                        ],
                    }
                ]
            },
        )
        self.assertEqual(total, 3)
        self.assertEqual(trip.num_days, 3)
        self.assertEqual(len(trip.destinations), 2)
        dests = sorted(trip.destinations, key=lambda d: d.sort_order)
        self.assertEqual(dests[0].name, "Kuala Lumpur")
        self.assertEqual(dests[0].start_day, 1)
        self.assertEqual(dests[0].country_code, "my")
        self.assertEqual(dests[1].name, "Malacca")
        self.assertEqual(dests[1].start_day, 3)
        self.assertIn("Malaysia", trip.location)

    def test_simple_mode_plan(self):
        plan = parse_route_plan({"mode": "simple", "cities": [{"name": "Paris", "days": 4}]})
        self.assertEqual(len(plan), 1)
        flat = flatten_route_plan(plan)
        self.assertEqual(flat[0][0], "Paris")
        self.assertEqual(flat[0][3], 1)
        self.assertEqual(flat[0][2], 4)

    def test_vietnam_country_inference(self):
        from app.services.geocode import infer_country_code
        self.assertEqual(infer_country_code("Hanoi, Vietnam"), "vn")
        self.assertEqual(infer_country_code("Hoa Lu"), "vn")

    def test_trip_to_route_plan_roundtrip(self):
        trip = Trip(name="Test", date="2026-01-01", location="", share_code="xyz789", num_days=6)
        trip.destinations = [
            TripDestination(name="Kuala Lumpur", country_code="my", sort_order=0, start_day=1),
            TripDestination(name="Malacca", country_code="my", sort_order=1, start_day=3),
            TripDestination(name="Bangkok", country_code="th", sort_order=2, start_day=4),
        ]
        data = trip_to_route_plan(trip)
        plan = parse_route_plan(data)
        flat = flatten_route_plan(plan)
        self.assertEqual([d for _n, _c, d, _s in flat], [2, 1, 3])
        self.assertEqual([s for _n, _c, _d, s in flat], [1, 3, 4])

    def test_trip_to_route_plan_single_city_simple_mode(self):
        trip = Trip(
            name="London trip",
            date="2026-07-17",
            location="United Kingdom: London",
            share_code="0byaxoo8j3",
            num_days=5,
        )
        trip.destinations = [
            TripDestination(name="London Apprentice", country_code="gb", sort_order=0, start_day=1),
        ]
        data = trip_to_route_plan(trip)
        self.assertEqual(data["mode"], "simple")
        self.assertEqual(len(data["cities"]), 1)
        self.assertEqual(data["cities"][0]["name"], "London Apprentice")
        self.assertEqual(data["cities"][0]["days"], 5)

    def test_reorder_preserves_start_days(self):
        plan = parse_route_plan(
            {
                "countries": [
                    {"name": "Thailand", "code": "th", "cities": [{"name": "Bangkok", "days": 2}]},
                    {"name": "Malaysia", "code": "my", "cities": [{"name": "Kuala Lumpur", "days": 3}]},
                ]
            }
        )
        flat = flatten_route_plan(plan)
        self.assertEqual([s for _n, _c, _d, s in flat], [1, 3])


if __name__ == "__main__":
    unittest.main()
