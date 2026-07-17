"""Tests for expense currency helpers."""

import unittest

from app.services.expenses import (
    compute_balances,
    default_expense_currency,
    format_cents,
    normalize_currency,
)


class ExpenseCurrencyTests(unittest.TestCase):
    def test_normalize_currency_defaults_unknown(self):
        self.assertEqual(normalize_currency("MYR"), "MYR")
        self.assertEqual(normalize_currency("xyz"), "USD")

    def test_format_cents_uses_symbol(self):
        self.assertEqual(format_cents(2450, "USD"), "$24.50")
        self.assertEqual(format_cents(2450, "MYR"), "RM 24.50")
        self.assertEqual(format_cents(2450, "THB"), "฿24.50")

    def test_default_expense_currency_from_trip_country(self):
        from app.models import Trip, TripDestination

        trip = Trip(name="Asia", date="2026-07-15", location="", share_code="test123456")
        trip.destinations = [
            TripDestination(name="Kuala Lumpur", country_code="my", start_day=1, sort_order=0),
        ]
        self.assertEqual(default_expense_currency(trip), "MYR")


if __name__ == "__main__":
    unittest.main()
