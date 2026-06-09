"""weather tool — current weather for a location, via wttr.in (no API key).

Wttr.in is a free console-oriented weather service that takes a
location as the URL path and returns JSON. We hit
`https://wttr.in/<location>?format=j1` and pluck out the fields the
LLM needs to summarize in a sentence.

The LLM is told to call this with a city name, an airport code, or
a coordinate pair (lat,lon). If the user says "today's weather in
Hong Kong", the agent should call `weather(location="Hong Kong")`.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

import httpx

from app.tools._stubs import BaseTool

logger = logging.getLogger(__name__)

# wttr.in returns ~3-5 KB of JSON for `?format=j1`. We cap at 16 KB
# to be safe in case of weirdness.
MAX_BYTES = 16 * 1024
DEFAULT_TIMEOUT_S = 12.0
USER_AGENT = "GundamHalo/0.1 (+https://github.com/ihateusingai-beep/gundam-halo)"


def _summarize_weather(payload: dict) -> str:
    """Extract the fields a human (or LLM) cares about from wttr.in's
    `current_condition[0]` block.

    We deliberately keep this conservative — we don't try to invent a
    natural-language summary; we just format the raw numbers in a way
    that's easy for the LLM to read and re-summarize in a sentence.
    """
    try:
        current = payload["current_condition"][0]
        area = payload.get("nearest_area", [{}])[0]
        city = ", ".join(
            x
            for x in (
                area.get("areaName", [{}])[0].get("value"),
                area.get("region", [{}])[0].get("value"),
                area.get("country", [{}])[0].get("value"),
            )
            if x
        ) or "?"
        desc = current.get("weatherDesc", [{}])[0].get("value", "?")
        temp_c = current.get("temp_C", "?")
        feels_c = current.get("FeelsLikeC", "?")
        humidity = current.get("humidity", "?")
        wind_kmph = current.get("windspeedKmph", "?")
        wind_dir = current.get("winddir16Point", "?")
        visibility_km = current.get("visibility", "?")
        pressure = current.get("pressure", "?")
        cloud_cover = current.get("cloudcover", "?")
        observed = current.get("observation_time", "?")

        # Today's high/low
        try:
            today = payload["weather"][0]
            high_c = today.get("maxtempC", "?")
            low_c = today.get("mintempC", "?")
            sunrise = today.get("astronomy", [{}])[0].get("sunrise", "?")
            sunset = today.get("astronomy", [{}])[0].get("sunset", "?")
        except (KeyError, IndexError):
            high_c = low_c = sunrise = sunset = "?"

        return (
            f"Location: {city}\n"
            f"Observed: {observed} UTC\n"
            f"Conditions: {desc}\n"
            f"Temperature: {temp_c}°C (feels like {feels_c}°C)\n"
            f"Today: high {high_c}°C / low {low_c}°C\n"
            f"Humidity: {humidity}%\n"
            f"Wind: {wind_kmph} km/h {wind_dir}\n"
            f"Visibility: {visibility_km} km\n"
            f"Pressure: {pressure} mb\n"
            f"Cloud cover: {cloud_cover}%\n"
            f"Sunrise: {sunrise} · Sunset: {sunset}"
        )
    except (KeyError, IndexError, TypeError) as e:
        return f"(could not parse wttr.in payload: {e})"


class WeatherTool(BaseTool):
    """Get current weather for a location. No API key needed."""

    name = "weather"
    description = (
        "Get the current weather for a location. Pass a city name "
        "(e.g. 'Hong Kong'), an airport code ('HKG'), or a coordinate "
        "pair ('22.3,114.2'). Returns current conditions, today's "
        "high/low, humidity, wind, and sunrise/sunset. Data is "
        "fetched from wttr.in (no API key needed)."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": (
                    "City name, airport code, or 'lat,lon'. Examples: "
                    "'Hong Kong', 'HKG', 'Tokyo', '22.3,114.2'."
                ),
            },
        },
        "required": ["location"],
    }

    async def run(self, location: str, **_: Any) -> str:
        if not isinstance(location, str) or not location.strip():
            return "Error: 'location' is required"
        location = location.strip()
        # wttr.in uses + for spaces, but httpx will encode; use a simple
        # URL with the raw location. wttr.in handles both.
        url = f"https://wttr.in/{location}?format=j1&lang=en"

        try:
            async with httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT_S,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                raw = resp.content[:MAX_BYTES]
                payload = json.loads(raw.decode("utf-8", errors="replace"))

            summary = _summarize_weather(payload)
            return f"Source: wttr.in (no API key)\n{summary}"
        except httpx.TimeoutException:
            return f"Error: weather service timed out for {location!r}"
        except httpx.HTTPStatusError as e:
            return f"Error: weather service returned HTTP {e.response.status_code}"
        except json.JSONDecodeError as e:
            return f"Error: weather service returned non-JSON response — {e}"
        except Exception as e:  # noqa: BLE001
            logger.exception("weather lookup failed")
            return f"Error: unexpected failure — {e}"


__all__ = ["WeatherTool"]
