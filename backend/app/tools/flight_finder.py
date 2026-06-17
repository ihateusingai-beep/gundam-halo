"""flight_finder tool — URL builder for Google Flights searches.

Sprint 27 (per `docs/FEATURE-SPEC-SPRINT27.md` §4.2 Track 27.3).

Mark-XL's `flight_finder.py` uses Selenium to scrape
Google Flights' rendered HTML. This is fragile (the
DOM changes every 3-6 months) and adds a heavy
`playwright`/`selenium` dep that Gundam Halo's venv
doesn't carry.

**Sprint 27 ships a more honest v0.1**: instead of
pretending we can extract structured flight data
without a paid API key, the tool builds a Google
Flights URL + returns a TTS-friendly summary that
the user can open in their browser. The agent's
NativeReAct loop can then optionally call
`webbrowser.open()` via the `open_app` tool to
launch the URL.

The tool is still useful — it converts messy user
input ("next Tuesday", "HKG to TPE") into a clean
date + IATA code + URL. The user gets a concrete
next step ("open this URL in your browser") rather
than a brittle auto-extraction that breaks every
3-6 months.

Future work (Sprint 31+): if the user adds a paid
flight API key (aviationstack, serpapi, Skyscanner
Business), the tool can grow a second path that
returns real flight data. The current
"URL builder" path stays as a fallback.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.tools._stubs import BaseTool

logger = logging.getLogger(__name__)

# Common IATA airport codes for the user's most likely
# routes. This is NOT a complete database; it's a hint
# for the LLM when it sees a city name like "Hong Kong"
# in the user's request. The full IATA database is
# ~9000 entries; we list the ~30 most relevant for
# the Cantonese-speaking user (HKG, TPE, HND, NRT,
# ICN, PEK, PVG, CAN, SZX, etc.).
AIRPORT_CODES: Dict[str, str] = {
    # Greater China
    "hong kong": "HKG", "hkg": "HKG",
    "taipei": "TPE", "tpe": "TPE",
    "tokyo": "HND", "hnd": "HND", "narita": "NRT", "nrt": "NRT",
    "osaka": "KIX", "kix": "KIX",
    "seoul": "ICN", "icn": "ICN",
    "beijing": "PEK", "pek": "PEK",
    "shanghai": "PVG", "pvg": "PVG",
    "guangzhou": "CAN", "can": "CAN",
    "shenzhen": "SZX", "szx": "SZX",
    "macau": "MFM", "mfm": "MFM",
    "singapore": "SIN", "sin": "SIN",
    "bangkok": "BKK", "bkk": "BKK",
    "kuala lumpur": "KUL", "kul": "KUL",
    "manila": "MNL", "mnl": "MNL",
    "jakarta": "CGK", "cgk": "CGK",
    "ho chi minh": "SGN", "sgn": "SGN",
    "hanoi": "HAN", "han": "HAN",
    # English-speaking / common routes
    "london": "LHR", "lhr": "LHR",
    "new york": "JFK", "jfk": "JFK",
    "los angeles": "LAX", "lax": "LAX",
    "san francisco": "SFO", "sfo": "SFO",
    "vancouver": "YVR", "yvr": "YVR",
    "sydney": "SYD", "syd": "SYD",
    "melbourne": "MEL", "mel": "MEL",
    "auckland": "AKL", "akl": "AKL",
}

# Relative date tokens (English) → offset days
RELATIVE_DATES: Dict[str, int] = {
    "today": 0,
    "tomorrow": 1,
    "day after tomorrow": 2,
    "next week": 7,
    "next monday": -1,  # special-cased below
    "next tuesday": -1,
    "next wednesday": -1,
    "next thursday": -1,
    "next friday": -1,
    "next saturday": -1,
    "next sunday": -1,
}

# Weekday names for "next <weekday>" resolution
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _resolve_to_iata(location: str) -> str:
    """Resolve a city name (e.g. "Hong Kong") to an
    IATA code (e.g. "HKG"). Falls back to uppercasing
    the input if it's already a 3-letter IATA code.
    """
    if not location:
        return ""
    s = location.strip().lower()
    if s in AIRPORT_CODES:
        return AIRPORT_CODES[s]
    # Already a 3-letter IATA code?
    if len(location.strip()) == 3 and location.strip().isalpha():
        return location.strip().upper()
    # Unknown city — return the input uppercased so
    # the URL is at least deterministic. The user can
    # correct via the URL.
    return location.strip().upper()


def _resolve_date(date_str: str) -> Optional[str]:
    """Resolve a date string to YYYY-MM-DD format.

    Supports:
      - "today", "tomorrow", "day after tomorrow"
      - "next week" (= +7 days)
      - "next <weekday>" (= next occurrence of that weekday)
      - "YYYY-MM-DD" (already valid, return as-is)
      - "DD/MM/YYYY" or "MM/DD/YYYY" (parse with heuristic)
    Returns None if the input can't be parsed.
    """
    if not date_str:
        return None
    s = date_str.strip().lower()

    # Absolute date YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str.strip()):
        try:
            datetime.strptime(date_str.strip(), "%Y-%m-%d")
            return date_str.strip()
        except ValueError:
            return None

    # Relative date
    if s in RELATIVE_DATES:
        offset = RELATIVE_DATES[s]
        if offset >= 0:
            target = datetime.now() + timedelta(days=offset)
            return target.strftime("%Y-%m-%d")

    # "next <weekday>"
    if s.startswith("next ") and s[5:] in WEEKDAYS:
        target_weekday = WEEKDAYS.index(s[5:])
        today = datetime.now()
        days_ahead = target_weekday - today.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        target = today + timedelta(days=days_ahead)
        return target.strftime("%Y-%m-%d")

    # DD/MM/YYYY or MM/DD/YYYY — heuristic: try both
    for fmt in ("%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def _build_google_flights_url(
    origin: str,
    destination: str,
    date: str,
    return_date: Optional[str] = None,
    passengers: int = 1,
) -> str:
    """Build a Google Flights search URL.

    The URL format is stable as of 2026-06-17; Google
    Flights uses a query-string-based interface that
    survives most redesigns.
    """
    # Format: https://www.google.com/travel/flights?q=...
    params = [
        f"from={origin}",
        f"to={destination}",
        f"date={date}",
    ]
    if return_date:
        params.append(f"return={return_date}")
    if passengers > 1:
        params.append(f"adults={passengers}")
    query = " ".join(params)
    return f"https://www.google.com/travel/flights?q={query}"


class FlightFinderError(RuntimeError):
    """Raised on flight search errors."""


class FlightFinderTool(BaseTool):
    """Build a Google Flights search URL for a route.

    Returns a TTS-friendly summary with the resolved
    IATA codes, dates, and a clickable URL. The agent's
    NativeReAct loop can then call `open_app` or
    `apple_script` to open the URL in the user's
    default browser.

    Sprint 27 ships this as a URL builder (not a
    flight-data extractor) because the v0.1.x
    Gundam Halo venv doesn't carry `playwright` or
    a paid flight API key. The Mark-XL Selenium path
    was deemed too fragile for v0.1.5+. See the
    file-level docstring for the future work to
    add a paid-API path.
    """

    name = "flight_finder"
    description = (
        "Build a Google Flights search URL for a route. "
        "Pass IATA codes (HKG, TPE) or city names (Hong Kong, "
        "Taipei). Date can be 'today', 'tomorrow', 'next Tuesday', "
        "or 'YYYY-MM-DD'. Returns the resolved IATA codes, the "
        "date, and a Google Flights URL. The agent can then call "
        "`open_app` to launch the URL in the user's browser. "
        "This is a URL builder, not a flight-data extractor — "
        "the user opens the URL to see the actual flights."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "origin": {
                "type": "string",
                "description": (
                    "Departure city or IATA code. "
                    "Examples: 'HKG', 'Hong Kong', 'TPE', 'Tokyo'."
                ),
            },
            "destination": {
                "type": "string",
                "description": (
                    "Arrival city or IATA code. "
                    "Examples: 'HKG', 'Taipei', 'NRT'."
                ),
            },
            "date": {
                "type": "string",
                "description": (
                    "Departure date. Examples: '2026-06-24', 'tomorrow', "
                    "'next Tuesday'."
                ),
            },
            "return_date": {
                "type": "string",
                "description": (
                    "Return date for round trips (optional). Same "
                    "format as `date`."
                ),
            },
            "passengers": {
                "type": "integer",
                "description": "Number of passengers (default 1).",
            },
            "cabin": {
                "type": "string",
                "enum": ["economy", "premium", "business", "first"],
                "description": (
                    "Cabin class (default economy). Informational "
                    "only — the URL builder doesn't pass cabin to "
                    "Google Flights; the user selects it in the "
                    "browser."
                ),
            },
        },
        "required": ["origin", "destination", "date"],
    }

    async def run(
        self,
        origin: str,
        destination: str,
        date: str,
        return_date: Optional[str] = None,
        passengers: int = 1,
        cabin: str = "economy",
        **_: Any,
    ) -> str:
        # Validate
        if not isinstance(origin, str) or not origin.strip():
            return "Error: 'origin' is required and must be a non-empty string"
        if not isinstance(destination, str) or not destination.strip():
            return "Error: 'destination' is required and must be a non-empty string"
        if not isinstance(date, str) or not date.strip():
            return "Error: 'date' is required and must be a non-empty string"

        # Resolve to IATA codes
        origin_code = _resolve_to_iata(origin)
        dest_code = _resolve_to_iata(destination)
        if not origin_code or not dest_code:
            return f"Error: could not resolve airports for {origin!r} → {destination!r}"

        # Resolve dates
        date_resolved = _resolve_date(date)
        if not date_resolved:
            return (
                f"Error: could not parse date {date!r}. "
                f"Use 'YYYY-MM-DD', 'today', 'tomorrow', or 'next <weekday>'."
            )
        return_date_resolved = None
        if return_date:
            return_date_resolved = _resolve_date(return_date)
            if not return_date_resolved:
                return f"Error: could not parse return_date {return_date!r}"

        # Build URL
        url = _build_google_flights_url(
            origin_code, dest_code, date_resolved, return_date_resolved, passengers
        )

        # Format the response
        trip_type = "round trip" if return_date_resolved else "one-way"
        passenger_label = "passenger" if passengers == 1 else "passengers"
        out = (
            f"Flight search: {origin} ({origin_code}) → "
            f"{destination} ({dest_code}) on {date_resolved}, "
            f"{cabin} class, {passengers} {passenger_label}, {trip_type}.\n"
            f"Google Flights URL: {url}\n"
            f"Open this URL in your browser to see the available flights. "
            f"The agent can call `open_app` to launch the URL automatically."
        )
        if return_date_resolved:
            out += f"\nReturn: {return_date_resolved}"
        return out


__all__ = ["FlightFinderTool", "FlightFinderError"]
