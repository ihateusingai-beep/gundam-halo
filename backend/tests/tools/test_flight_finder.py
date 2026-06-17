"""Tests for FlightFinderTool (Sprint 27 Track 27.3).

Per `docs/FEATURE-SPEC-SPRINT27.md` §4.2 Track 27.3.

Test categories:
  1. Schema + name
  2. IATA resolution (city name + IATA code)
  3. Date resolution (relative + absolute)
  4. URL builder (one-way + round-trip + multi-passenger)
  5. run() integration (happy path + error paths)
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.tools.flight_finder import (
    FlightFinderError,
    FlightFinderTool,
    _build_google_flights_url,
    _resolve_date,
    _resolve_to_iata,
)


# ---------------------------------------------------------------------------
# 1. Schema + name
# ---------------------------------------------------------------------------


class TestSchema:
    def test_name(self):
        assert FlightFinderTool().name == "flight_finder"

    def test_required_params(self):
        params = FlightFinderTool().parameters
        for p in ("origin", "destination", "date"):
            assert p in params["required"]


# ---------------------------------------------------------------------------
# 2. IATA resolution
# ---------------------------------------------------------------------------


class TestIATAResolution:
    def test_resolves_city_names(self):
        assert _resolve_to_iata("Hong Kong") == "HKG"
        assert _resolve_to_iata("Taipei") == "TPE"
        assert _resolve_to_iata("Tokyo") == "HND"
        assert _resolve_to_iata("Seoul") == "ICN"

    def test_resolves_iata_codes(self):
        assert _resolve_to_iata("HKG") == "HKG"
        assert _resolve_to_iata("tpe") == "TPE"  # case-insensitive
        assert _resolve_to_iata("NRT") == "NRT"

    def test_case_insensitive(self):
        assert _resolve_to_iata("hong kong") == "HKG"
        assert _resolve_to_iata("HONG KONG") == "HKG"
        assert _resolve_to_iata("HoNg KoNg") == "HKG"

    def test_passes_through_unknown_3letter(self):
        # 3-letter all-alpha that's not in our table → uppercase
        assert _resolve_to_iata("XYZ") == "XYZ"

    def test_unknown_city_uppercased(self):
        # Unknown multi-word city → just uppercase the input
        # (so the URL is at least deterministic, even if wrong)
        assert _resolve_to_iata("atlantis") == "ATLANTIS"

    def test_empty_input(self):
        assert _resolve_to_iata("") == ""


# ---------------------------------------------------------------------------
# 3. Date resolution
# ---------------------------------------------------------------------------


class TestDateResolution:
    def test_absolute_iso_date(self):
        assert _resolve_date("2026-06-24") == "2026-06-24"

    def test_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        assert _resolve_date("today") == today

    def test_tomorrow(self):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        assert _resolve_date("tomorrow") == tomorrow

    def test_day_after_tomorrow(self):
        day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        assert _resolve_date("day after tomorrow") == day_after

    def test_next_week(self):
        next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        assert _resolve_date("next week") == next_week

    def test_next_weekday(self):
        # "next tuesday" should resolve to a valid date
        result = _resolve_date("next tuesday")
        assert result is not None
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", result)

    def test_invalid_date_returns_none(self):
        assert _resolve_date("not a date") is None
        assert _resolve_date("2026-13-45") is None  # invalid month/day
        assert _resolve_date("") is None

    def test_dd_mm_yyyy(self):
        assert _resolve_date("24/06/2026") == "2026-06-24"

    def test_mm_dd_yyyy(self):
        assert _resolve_date("06/24/2026") == "2026-06-24"


# ---------------------------------------------------------------------------
# 4. URL builder
# ---------------------------------------------------------------------------


class TestURLBuilder:
    def test_one_way(self):
        url = _build_google_flights_url("HKG", "TPE", "2026-06-24")
        assert "from=HKG" in url
        assert "to=TPE" in url
        assert "date=2026-06-24" in url
        assert "return" not in url
        assert "adults" not in url

    def test_round_trip(self):
        url = _build_google_flights_url("HKG", "TPE", "2026-06-24", return_date="2026-07-01")
        assert "return=2026-07-01" in url

    def test_multi_passenger(self):
        url = _build_google_flights_url("HKG", "TPE", "2026-06-24", passengers=3)
        assert "adults=3" in url

    def test_single_passenger_no_adults_param(self):
        url = _build_google_flights_url("HKG", "TPE", "2026-06-24", passengers=1)
        assert "adults" not in url

    def test_base_url_is_google_flights(self):
        url = _build_google_flights_url("HKG", "TPE", "2026-06-24")
        assert url.startswith("https://www.google.com/travel/flights?")


import re  # for TestDateResolution.test_next_weekday


# ---------------------------------------------------------------------------
# 5. run() integration
# ---------------------------------------------------------------------------


class TestRun:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        tool = FlightFinderTool()
        out = await tool.run(
            origin="Hong Kong",
            destination="Taipei",
            date="2026-06-24",
        )
        assert "HKG" in out
        assert "TPE" in out
        assert "2026-06-24" in out
        assert "one-way" in out
        assert "google.com/travel/flights" in out

    @pytest.mark.asyncio
    async def test_round_trip(self):
        tool = FlightFinderTool()
        out = await tool.run(
            origin="HKG",
            destination="TPE",
            date="2026-06-24",
            return_date="2026-07-01",
            passengers=2,
            cabin="business",
        )
        assert "round trip" in out
        assert "2 passengers" in out
        assert "business" in out
        assert "adults=2" in out
        assert "return=2026-07-01" in out

    @pytest.mark.asyncio
    async def test_relative_date_resolution(self):
        tool = FlightFinderTool()
        out = await tool.run(origin="HKG", destination="TPE", date="tomorrow")
        # Tomorrow's date should appear
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        assert tomorrow in out

    @pytest.mark.asyncio
    async def test_rejects_empty_origin(self):
        out = await FlightFinderTool().run(
            origin="", destination="TPE", date="2026-06-24"
        )
        assert "Error" in out
        assert "origin" in out

    @pytest.mark.asyncio
    async def test_rejects_empty_destination(self):
        out = await FlightFinderTool().run(
            origin="HKG", destination="", date="2026-06-24"
        )
        assert "Error" in out
        assert "destination" in out

    @pytest.mark.asyncio
    async def test_rejects_empty_date(self):
        out = await FlightFinderTool().run(
            origin="HKG", destination="TPE", date=""
        )
        assert "Error" in out
        assert "date" in out

    @pytest.mark.asyncio
    async def test_rejects_invalid_date(self):
        out = await FlightFinderTool().run(
            origin="HKG", destination="TPE", date="not a date"
        )
        assert "Error" in out
        assert "date" in out.lower()

    @pytest.mark.asyncio
    async def test_rejects_invalid_return_date(self):
        out = await FlightFinderTool().run(
            origin="HKG", destination="TPE",
            date="2026-06-24", return_date="not a date"
        )
        assert "Error" in out
        assert "return_date" in out
