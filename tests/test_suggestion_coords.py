"""Tests for suggestion location formatting and coordinates."""

import unittest

from app.services.suggestions import (
    _curated_suggestions,
    _format_suggestion_location,
    _suggestion_from_idea,
)


class SuggestionLocationTests(unittest.TestCase):
    def test_format_suggestion_location_includes_city_and_country(self):
        loc = _format_suggestion_location(
            {"location": "Bonifacio"},
            "Corsica",
            country_code="fr",
        )
        self.assertIn("Bonifacio", loc)
        self.assertIn("Corsica", loc)
        self.assertIn("France", loc)

    def test_curated_corsica_includes_coordinates(self):
        suggestions = _curated_suggestions("Corsica", 1, 4, country_code="fr")
        self.assertGreaterEqual(len(suggestions), 4)
        with_coords = [s for s in suggestions if s.latitude is not None and s.longitude is not None]
        self.assertGreaterEqual(len(with_coords), 4)
        self.assertIn("France", suggestions[0].location)

    def test_suggestion_from_idea_reads_lat_lng(self):
        s = _suggestion_from_idea(
            {"title": "Test Place", "location": "Calvi", "lat": 42.5, "lng": 8.7},
            day=1,
            city_label="Corsica",
            country_code="fr",
        )
        self.assertEqual(s.latitude, 42.5)
        self.assertEqual(s.longitude, 8.7)


if __name__ == "__main__":
    unittest.main()
