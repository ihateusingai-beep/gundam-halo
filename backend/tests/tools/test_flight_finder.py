"""Tests for FlightFinderTool (Sprint 27 Track 27.3, Sprint 30 Track B).

Per `docs/FEATURE-SPEC-SPRINT27.md` §4.2 Track 27.3
and `docs/FEATURE-SPEC-SPRINT30.md` §4.2.

Test categories:
  1. Schema + name
  2. IATA resolution (city name + IATA code)
  3. Date resolution (relative + absolute)
  4. URL builder (one-way + round-trip + multi-passenger)
  5. run() integration — URL builder fallback (Sprint 27
     behavior, now exercised when api_key is empty)
  6. run() integration — aviationstack happy path
     (Sprint 30 Track B)
  7. run() integration — aviationstack error envelope
     / HTTP error / transport error → URL builder fallback
  8. TTS formatter unit tests (per-flight prose + top-N
     sort + empty list)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import httpx
import pytest
import respx

from app.core.config import FlightFinderConfig
from app.tools.flight_finder import (
    AVIATIONSTACK_BASE_URL,
    FlightFinderError,
    FlightFinderTool,
    _build_google_flights_url,
    _fetch_from_aviationstack,
    _format_flight_for_tts,
    _resolve_date,
    _resolve_to_iata,
    _summarise_flights_for_tts,
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


# ---------------------------------------------------------------------------
# 6. _fetch_from_aviationstack — direct unit tests (mocked httpx)
# ---------------------------------------------------------------------------


SAMPLE_FLIGHT = {
    "airline": {"name": "Cathay Pacific", "iata": "CX"},
    "flight": {"iata": "CX 450", "number": "450"},
    "departure": {
        "airport": "HKG",
        "scheduled": "2026-06-24T14:30:00+00:00",
    },
    "arrival": {
        "airport": "TPE",
        "scheduled": "2026-06-24T16:45:00+00:00",
    },
    "flight_price": "$420",
}

SAMPLE_FLIGHT_2 = {
    "airline": {"name": "EVA Air", "iata": "BR"},
    "flight": {"iata": "BR 892", "number": "892"},
    "departure": {
        "airport": "HKG",
        "scheduled": "2026-06-24T18:00:00+00:00",
    },
    "arrival": {
        "airport": "TPE",
        "scheduled": "2026-06-24T20:15:00+00:00",
    },
    "flight_price": "$380",
}


class TestFetchFromAviationstack:
    """Unit tests for `_fetch_from_aviationstack` (mocked httpx via respx).

    The helper returns the raw `data` list from the
    aviationstack response, or raises `FlightFinderError`
    on aviationstack's `{"error": ...}` envelope.
    """

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_data_list_on_success(self):
        respx.get(AVIATIONSTACK_BASE_URL).mock(
            return_value=httpx.Response(200, json={"data": [SAMPLE_FLIGHT, SAMPLE_FLIGHT_2]})
        )
        result = await _fetch_from_aviationstack("HKG", "TPE", "2026-06-24", "TEST_KEY")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["airline"]["name"] == "Cathay Pacific"
        assert result[1]["flight_price"] == "$380"

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_on_error_envelope(self):
        # aviationstack returns {"error": {...}} with HTTP 200
        # when the key is invalid / rate-limited.
        respx.get(AVIATIONSTACK_BASE_URL).mock(
            return_value=httpx.Response(
                200,
                json={"error": {"code": "invalid_access_key", "info": "You have not supplied a valid API Access Key."}},
            )
        )
        with pytest.raises(FlightFinderError) as excinfo:
            await _fetch_from_aviationstack("HKG", "TPE", "2026-06-24", "BAD_KEY")
        assert "valid API Access Key" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 7. TTS formatter unit tests (per spec §4.2 example prose format)
# ---------------------------------------------------------------------------


class TestFormatFlightForTTS:
    """Unit tests for `_format_flight_for_tts`.

    Verifies the prose contract:
        "Flight CX 450 on Cathay Pacific, departing HKG
         at 14:30, arriving TPE at 16:45, price $420."
    """

    def test_full_flight_format(self):
        out = _format_flight_for_tts(SAMPLE_FLIGHT)
        assert "Flight CX 450" in out
        assert "Cathay Pacific" in out
        assert "HKG" in out
        assert "TPE" in out
        assert "$420" in out
        assert out.endswith(".")

    def test_omits_price_when_missing(self):
        # Free tier — no `flight_price` field.
        flight_no_price = {k: v for k, v in SAMPLE_FLIGHT.items() if k != "flight_price"}
        out = _format_flight_for_tts(flight_no_price)
        assert "$" not in out
        assert "Cathay Pacific" in out

    def test_sorts_by_price_and_caps_top_n(self):
        # 3 flights, top_n=2 → only the 2 cheapest returned,
        # sorted ascending ($380 before $420).
        flight_expensive = {**SAMPLE_FLIGHT, "flight_price": "$999"}
        flights = [SAMPLE_FLIGHT, SAMPLE_FLIGHT_2, flight_expensive]
        out = _summarise_flights_for_tts(flights, "HKG", "TPE", "2026-06-24", top_n=2)
        assert "Top 2 flights" in out
        assert "$999" not in out  # capped
        assert out.index("BR 892") < out.index("CX 450")  # sorted by price


# ---------------------------------------------------------------------------
# 8. run() integration — aviationstack path (mocked httpx via respx)
# ---------------------------------------------------------------------------


def _api_key_config(api_key: str = "TEST_KEY", api_provider: str = "aviationstack", top_n: int = 5) -> FlightFinderConfig:
    """Build a FlightFinderConfig for testing the aviationstack path."""
    return FlightFinderConfig(
        enabled=True,
        api_key=api_key,
        api_provider=api_provider,
        top_n=top_n,
    )


class TestRunAviationstack:
    """Integration tests for `FlightFinderTool.run()` with the
    aviationstack API mocked via respx.

    These tests verify:
      - Happy path returns TTS-friendly prose (sorted by price)
      - Error envelope → URL builder fallback (with note)
      - HTTP 4xx → URL builder fallback (with note)
      - Timeout / transport error → URL builder fallback (with note)
      - Empty data → "No flights found" message
      - Unknown api_provider → URL builder fallback (no API call)
    """

    @pytest.mark.asyncio
    @respx.mock
    async def test_happy_path_returns_top_n_prose(self):
        respx.get(AVIATIONSTACK_BASE_URL).mock(
            return_value=httpx.Response(200, json={"data": [SAMPLE_FLIGHT, SAMPLE_FLIGHT_2]})
        )
        tool = FlightFinderTool(config=_api_key_config(api_key="TEST_KEY", top_n=2))
        out = await tool.run(origin="HKG", destination="TPE", date="2026-06-24")
        assert "Top 2 flights from HKG to TPE on 2026-06-24" in out
        assert "Cathay Pacific" in out
        assert "EVA Air" in out
        # Sorted by price: $380 (BR 892) before $420 (CX 450)
        assert out.index("BR 892") < out.index("CX 450")
        # No URL builder fallback marker
        assert "google.com/travel/flights" not in out
        assert "Falling back" not in out

    @pytest.mark.asyncio
    @respx.mock
    async def test_falls_back_on_error_envelope(self):
        # aviationstack returns {"error": ...} with HTTP 200.
        respx.get(AVIATIONSTACK_BASE_URL).mock(
            return_value=httpx.Response(
                200,
                json={"error": {"code": "rate_limited", "info": "Monthly quota exceeded"}},
            )
        )
        tool = FlightFinderTool(config=_api_key_config(api_key="TEST_KEY"))
        out = await tool.run(origin="HKG", destination="TPE", date="2026-06-24")
        assert "google.com/travel/flights" in out
        assert "Falling back to URL builder" in out
        assert "quota" in out.lower()

    @pytest.mark.asyncio
    @respx.mock
    async def test_falls_back_on_http_401(self):
        respx.get(AVIATIONSTACK_BASE_URL).mock(return_value=httpx.Response(401))
        tool = FlightFinderTool(config=_api_key_config(api_key="BAD_KEY"))
        out = await tool.run(origin="HKG", destination="TPE", date="2026-06-24")
        assert "google.com/travel/flights" in out
        assert "Falling back to URL builder" in out

    @pytest.mark.asyncio
    @respx.mock
    async def test_falls_back_on_timeout(self):
        respx.get(AVIATIONSTACK_BASE_URL).mock(side_effect=httpx.TimeoutException("timeout"))
        tool = FlightFinderTool(config=_api_key_config(api_key="TEST_KEY"))
        out = await tool.run(origin="HKG", destination="TPE", date="2026-06-24")
        assert "google.com/travel/flights" in out
        assert "Falling back to URL builder" in out

    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_data_returns_no_flights_message(self):
        respx.get(AVIATIONSTACK_BASE_URL).mock(return_value=httpx.Response(200, json={"data": []}))
        tool = FlightFinderTool(config=_api_key_config(api_key="TEST_KEY"))
        out = await tool.run(origin="HKG", destination="TPE", date="2026-06-24")
        assert "No flights found" in out
        assert "HKG" in out and "TPE" in out

    @pytest.mark.asyncio
    async def test_unknown_provider_falls_back_without_api_call(self):
        # No respx mock registered — if the tool makes an HTTP
        # call, respx will raise on the unmatched route. This
        # test asserts the URL builder fallback fires before
        # any HTTP call when api_provider is unsupported.
        tool = FlightFinderTool(config=_api_key_config(api_provider="serpapi"))
        out = await tool.run(origin="HKG", destination="TPE", date="2026-06-24")
        assert "google.com/travel/flights" in out
        # No fallback NOTE since we never tried the API
        assert "Falling back to URL builder" not in out
