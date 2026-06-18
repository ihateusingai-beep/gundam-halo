"""flight_finder tool — aviationstack real extractor + URL builder fallback.

Sprint 27 (per `docs/FEATURE-SPEC-SPRINT27.md` §4.2 Track 27.3)
shipped this tool as a **URL builder** — no flight-data
extraction. The Mark-XL Selenium-based extractor was too
fragile (DOM changes every 3-6 months) and pulled in a
heavy `playwright` dep Gundam Halo's venv doesn't carry.

**Sprint 30 Track B** (per `docs/FEATURE-SPEC-SPRINT30.md`
§4.2) replaces the URL-only behavior with a real flight-
data extractor that calls the **aviationstack** API
(free tier: 100 requests/month; paid: $50/month for
10,000 requests). The URL builder stays as the
fallback when:

  1. The user hasn't set `[tools.flight_finder] api_key
     = "..."` in `~/.gundam-halo/config.toml` (no paid
     account, free-tier testing, or opt-out).
  2. The aviationstack call fails — HTTP 401/403/429
     (auth/rate-limit), 5xx (transient outage), or
     timeout. The user gets a "API failed; falling back
     to URL builder" note plus the URL they can open
     in their browser.

The aviationstack response is parsed into TTS-friendly
prose via `_format_flight_for_tts()`:

  "Flight CX 450 on Cathay Pacific, departing HKG at
   14:30, arriving TPE at 16:45, price $420."

The top `FlightFinderConfig.top_n` (default 5) flights
are returned, sorted by price (when available) then by
scheduled departure time. `httpx` is the HTTP client
(already in the venv per Sprint 17b); the import is
**lazy** so the test suite can mock the HTTP layer
without pulling in httpx at module import time.

The URL builder still does the messy work of resolving
"next Tuesday" / "HKG" / "Hong Kong" into clean IATA
codes + ISO dates. The agent's NativeReAct loop can
then call `open_app` to launch the URL in the user's
browser.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.tools._stubs import BaseTool

logger = logging.getLogger(__name__)

# aviationstack endpoint (HTTP — the free tier does
# not require HTTPS; the paid tier does but works
# over HTTPS too). Track B ships HTTP for the free
# tier; the user can switch to HTTPS by changing
# this constant if they want paid-tier guarantees.
AVIATIONSTACK_BASE_URL = "http://api.aviationstack.com/v1/flights"
# Default HTTP timeout (seconds). aviationstack's free
# tier is usually <2s but a slow cluster can take
# 5-10s; 30s is generous and matches httpx's docs.
DEFAULT_API_TIMEOUT_S = 30.0

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


# ---------------------------------------------------------------------------
# aviationstack integration (Sprint 30 Track B)
# ---------------------------------------------------------------------------


async def _fetch_from_aviationstack(
    origin: str,
    destination: str,
    date: str,
    api_key: str,
    timeout_s: float = DEFAULT_API_TIMEOUT_S,
) -> List[Dict[str, Any]]:
    """Call the aviationstack API and return the flight list.

    Args:
        origin: Departure IATA code (e.g. "HKG").
        destination: Arrival IATA code (e.g. "TPE").
        date: Departure date in YYYY-MM-DD format.
        api_key: The user's aviationstack access_key.
        timeout_s: HTTP timeout in seconds (default 30s).

    Returns:
        A list of flight dicts (the raw `data` field from
        the aviationstack response). Each dict has the
        shape documented at
        https://aviationstack.com/documentation
        (fields: `airline.name`, `flight.iata`,
         `departure.airport`, `departure.scheduled`,
         `arrival.airport`, `arrival.scheduled`,
         `flight_price`).

    Raises:
        FlightFinderError: On aviationstack-reported
            errors (auth failure, rate limit, invalid
            params — aviationstack returns
            `{"error": {"code": ..., "info": ...}}` in
            these cases).
        httpx.HTTPStatusError: On non-2xx HTTP status
            codes not covered by aviationstack's
            `{"error": ...}` envelope (e.g. 5xx with no
            JSON body, or transport errors). The caller
            is expected to catch this and fall back to
            the URL builder.
        httpx.RequestError: On transport errors
            (connection refused, DNS failure, timeout).
            The caller is expected to catch this and fall
            back to the URL builder.
    """
    # Lazy-import httpx so the module is importable in
    # test environments that mock httpx at the
    # `_fetch_from_aviationstack` call boundary
    # (respx intercepts at httpx.AsyncClient level, not
    # at import time, but lazy-import keeps the module
    # surface clean).
    import httpx  # type: ignore

    params: Dict[str, str] = {
        "access_key": api_key,
        "dep_iata": origin,
        "arr_iata": destination,
        "flight_date": date,
    }
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.get(AVIATIONSTACK_BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    # aviationstack returns {"error": {"code": ...,
    # "info": ...}} on auth failure / rate limit /
    # invalid params even when the HTTP status is 200.
    # Catch this envelope before returning data.
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        if isinstance(err, dict):
            info = err.get("info", "unknown error")
        else:
            info = str(err)
        raise FlightFinderError(f"aviationstack error: {info}")

    # Normal path: `{"data": [...]}` envelope.
    if isinstance(data, dict):
        return data.get("data", [])
    # Unexpected shape (e.g. list at top level — defensive).
    return []


def _format_flight_for_tts(flight: Dict[str, Any]) -> str:
    """Format a single aviationstack flight dict as a
    TTS-friendly prose sentence.

    Example output:
        "Flight CX 450 on Cathay Pacific, departing HKG
         at 2026-06-24T14:30:00+00:00, arriving TPE at
         2026-06-24T16:45:00+00:00, price $420."

    The function is **defensive**: missing fields
    fall back to placeholders ("Unknown airline",
    "?") so a partial aviationstack response still
    renders something usable. The price field is
    omitted when absent (aviationstack's free tier
    doesn't include `flight_price`).

    Args:
        flight: A single flight dict from aviationstack
            (the element of the `data` list).

    Returns:
        A single TTS-friendly prose sentence ending
        in a period.
    """
    airline = (
        flight.get("airline", {}).get("name", "Unknown airline")
        if isinstance(flight.get("airline"), dict)
        else "Unknown airline"
    )
    flight_num = (
        flight.get("flight", {}).get("iata", "")
        if isinstance(flight.get("flight"), dict)
        else ""
    )
    dep = flight.get("departure", {}) or {}
    arr = flight.get("arrival", {}) or {}
    price = flight.get("flight_price", "")

    parts: List[str] = []
    if flight_num:
        parts.append(f"Flight {flight_num} on {airline}")
    else:
        parts.append(f"Flight on {airline}")
    parts.append(
        f"departing {dep.get('airport', '?')} at {dep.get('scheduled', '?')}"
    )
    parts.append(
        f"arriving {arr.get('airport', '?')} at {arr.get('scheduled', '?')}"
    )
    if price:
        parts.append(f"price {price}")
    return ", ".join(parts) + "."


def _summarise_flights_for_tts(
    flights: List[Dict[str, Any]],
    origin: str,
    destination: str,
    date: str,
    top_n: int = 5,
) -> str:
    """Sort + format the top-N flights as TTS-friendly prose.

    Args:
        flights: Raw flight list from aviationstack.
        origin: Departure IATA code (used in the
            prose header).
        destination: Arrival IATA code.
        date: Departure date (used in the header).
        top_n: How many flights to include in the
            prose summary (default 5; spec §4.3
            `FlightFinderConfig.top_n`).

    Returns:
        A single TTS-friendly prose string. Example:

            "Top 3 flights from HKG to TPE on 2026-06-24:
             The 1st cheapest is Flight CX 450 on Cathay
             Pacific, departing HKG at ..., arriving TPE
             at ..., price $420. The 2nd cheapest is ..."

    Sorting:
        Primary key = price (lower first; flights
        without a price sort last via the
        `999999` sentinel). Secondary key = scheduled
        departure time (earlier first) so flights
        with the same price are in chronological
        order.
    """
    if not flights:
        return f"No flights found from {origin} to {destination} on {date}."

    # Sort by price (missing → sentinel) then by
    # scheduled departure. We use a tuple key so the
    # Python sort is stable across runs.
    def _sort_key(f: Dict[str, Any]) -> tuple:
        price_raw = f.get("flight_price")
        # aviationstack sometimes returns price as a
        # string ("$420") or a number (420). Try to
        # parse; fall back to the sentinel if neither
        # works.
        price_val: float
        if isinstance(price_raw, (int, float)):
            price_val = float(price_raw)
        elif isinstance(price_raw, str):
            # Strip currency symbols + commas.
            cleaned = re.sub(r"[^\d.]", "", price_raw)
            try:
                price_val = float(cleaned)
            except ValueError:
                price_val = 999999.0
        else:
            price_val = 999999.0
        scheduled = (
            (f.get("departure") or {}).get("scheduled", "")
        )
        return (price_val, scheduled)

    sorted_flights = sorted(flights, key=_sort_key)

    top_flights = sorted_flights[: max(1, top_n)]
    ordinal_labels = [
        "1st", "2nd", "3rd", "4th", "5th",
        "6th", "7th", "8th", "9th", "10th",
    ]
    sentences: List[str] = [
        f"Top {len(top_flights)} flights from {origin} to {destination} on {date}:"
    ]
    for i, flight in enumerate(top_flights):
        label = ordinal_labels[i] if i < len(ordinal_labels) else f"{i + 1}th"
        sentences.append(
            f"The {label} cheapest is {_format_flight_for_tts(flight)}"
        )
    return " ".join(sentences)


class FlightFinderError(RuntimeError):
    """Raised on flight search errors.

    aviationstack returns an `{"error": {"code": ...,
    "info": ...}}` envelope on auth failure or
    rate-limit (HTTP 200 with a JSON body). The
    `_fetch_from_aviationstack` helper raises this
    exception with the `info` text so the caller can
    fall back to the URL builder with a useful error
    message.
    """


class FlightFinderTool(BaseTool):
    """Find flights between two airports.

    Sprint 30 Track B (per `docs/FEATURE-SPEC-SPRINT30.md`
    §4.2) ships a real aviationstack-based extractor
    with the Sprint 27 URL builder as a fallback. The
    user opts in to the real extractor by setting
    `[tools.flight_finder] api_key = "..."` in
    `~/.gundam-halo/config.toml`. Without a key (or
    when the API errors), the tool falls back to
    building a Google Flights URL the user opens in
    their browser — same behavior as Sprint 27.

    The aviationstack response is sorted by price
    (when available) then by scheduled departure
    time, and the top `top_n` (default 5) flights
    are returned as TTS-friendly prose.

    Returns TTS-friendly prose on the happy path:
    "Top 5 flights from HKG to TPE on 2026-06-24: The
     1st cheapest is Flight CX 450 on Cathay Pacific,
     departing HKG at ..., arriving TPE at ..., price
     $420. ..."

    Returns a Google Flights URL on the fallback
    path (no key / API error).
    """

    name = "flight_finder"
    description = (
        "Find flights between two airports. Pass IATA codes "
        "(HKG, TPE) or city names (Hong Kong, Taipei). Date can "
        "be 'today', 'tomorrow', 'next Tuesday', or 'YYYY-MM-DD'. "
        "If the aviationstack API key is configured in config.toml "
        "(`[tools.flight_finder] api_key = \"...\"`), the tool "
        "returns the top 5 flights as TTS-friendly prose, sorted "
        "by price then by departure time. Without an API key, the "
        "tool falls back to a Google Flights URL the user opens "
        "in their browser."
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
                    "format as `date`. Informational only — "
                    "aviationstack's free tier returns one-way "
                    "flights; round-trip is approximated by the "
                    "URL builder fallback."
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
                    "only — aviationstack's free tier doesn't filter "
                    "by cabin; the URL builder doesn't pass cabin to "
                    "Google Flights. The user selects it in the "
                    "browser or pays for a cabin-filtered plan."
                ),
            },
        },
        "required": ["origin", "destination", "date"],
    }

    def __init__(self, config: Any = None) -> None:
        """Initialise with optional `FlightFinderConfig`.

        The `config` arg is a `FlightFinderConfig` dataclass
        (from `app.core.config`) with fields:
          - enabled: bool (default True)
          - api_key: str (default "" — empty = URL builder
            fallback)
          - api_provider: str (default "aviationstack";
            reserved for future sprint when serpapi is added)
          - top_n: int (default 5; max 10)
        """
        super().__init__()
        self._config = config

    @property
    def api_key(self) -> str:
        """Read `api_key` from the FlightFinderConfig (or "")."""
        if self._config is None:
            return ""
        return getattr(self._config, "api_key", "")

    @property
    def api_provider(self) -> str:
        """Read `api_provider` from the FlightFinderConfig
        (or "aviationstack")."""
        if self._config is None:
            return "aviationstack"
        return getattr(self._config, "api_provider", "aviationstack")

    @property
    def top_n(self) -> int:
        """Read `top_n` from the FlightFinderConfig (or 5).
        Clamped to [1, 10]."""
        if self._config is None:
            return 5
        try:
            n = int(getattr(self._config, "top_n", 5))
        except (TypeError, ValueError):
            return 5
        return max(1, min(10, n))

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

        # Decide: aviationstack vs URL builder fallback.
        # No api_key → URL builder (Sprint 27 default).
        api_key = self.api_key.strip()
        if not api_key:
            logger.info(
                "flight_finder: no api_key configured; "
                "falling back to URL builder"
            )
            return self._format_url_builder_response(
                origin, origin_code, destination, dest_code,
                date_resolved, return_date_resolved, passengers, cabin,
            )

        # Try aviationstack (provider field reserved for
        # future sprint; only "aviationstack" is wired in
        # Track B).
        if self.api_provider != "aviationstack":
            logger.warning(
                "flight_finder: api_provider=%r not yet supported; "
                "falling back to URL builder",
                self.api_provider,
            )
            return self._format_url_builder_response(
                origin, origin_code, destination, dest_code,
                date_resolved, return_date_resolved, passengers, cabin,
            )

        try:
            flights = await _fetch_from_aviationstack(
                origin_code, dest_code, date_resolved, api_key,
            )
        except FlightFinderError as e:
            # Aviationstack returned {"error": ...}.
            # Fall back to the URL builder with a note
            # so the user knows why they're seeing the URL.
            logger.warning(
                "flight_finder: aviationstack returned error: %s; "
                "falling back to URL builder",
                e,
            )
            url_response = self._format_url_builder_response(
                origin, origin_code, destination, dest_code,
                date_resolved, return_date_resolved, passengers, cabin,
            )
            return f"{url_response}\n\n(Note: aviationstack API failed: {e}. Falling back to URL builder.)"
        except Exception as e:  # httpx.HTTPStatusError, RequestError, etc.
            # Transport / HTTP errors. Fall back with note.
            logger.warning(
                "flight_finder: aviationstack HTTP/transport error: %s; "
                "falling back to URL builder",
                e,
            )
            url_response = self._format_url_builder_response(
                origin, origin_code, destination, dest_code,
                date_resolved, return_date_resolved, passengers, cabin,
            )
            return f"{url_response}\n\n(Note: aviationstack API failed: {e}. Falling back to URL builder.)"

        # Happy path: format the top-N flights as prose.
        if not flights:
            return f"No flights found from {origin_code} to {dest_code} on {date_resolved}."

        return _summarise_flights_for_tts(
            flights, origin_code, dest_code, date_resolved, top_n=self.top_n,
        )

    def _format_url_builder_response(
        self,
        origin: str,
        origin_code: str,
        destination: str,
        dest_code: str,
        date_resolved: str,
        return_date_resolved: Optional[str],
        passengers: int,
        cabin: str,
    ) -> str:
        """Build the Sprint 27 URL-builder response string.

        Kept as a private helper so the URL builder
        stays as a fallback for both the
        "no api_key" and "api_key but API failed"
        cases. The format is identical to Sprint 27
        so the existing test suite assertions
        continue to pass.

        Args:
            origin: User's original origin input
                (e.g. "Hong Kong"). Used for the
                prose header.
            origin_code: Resolved IATA code
                (e.g. "HKG").
            destination, dest_code: As above.
            date_resolved: ISO date (YYYY-MM-DD).
            return_date_resolved: ISO date or None.
            passengers: Number of passengers (>= 1).
            cabin: Cabin class string.

        Returns:
            A TTS-friendly summary with the URL the
            user can open in their browser.
        """
        url = _build_google_flights_url(
            origin_code, dest_code, date_resolved,
            return_date_resolved, passengers,
        )
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


__all__ = ["FlightFinderTool", "FlightFinderError", "_fetch_from_aviationstack", "_format_flight_for_tts", "_summarise_flights_for_tts"]
