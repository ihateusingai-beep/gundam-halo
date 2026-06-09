"""Tests for WebFetchTool and WeatherTool (M7-Phase-1)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.tools.weather import WeatherTool
from app.tools.web_fetch import WebFetchTool


# ---------------------------------------------------------------------------
# WebFetchTool
# ---------------------------------------------------------------------------


class TestWebFetchTool:
    def test_schema(self):
        tool = WebFetchTool()
        assert tool.name == "web_fetch"
        assert "url" in tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_rejects_non_http_scheme(self):
        tool = WebFetchTool()
        result = await tool.run(url="file:///etc/passwd")
        assert "Error" in result
        assert "http(s)" in result

    @pytest.mark.asyncio
    async def test_rejects_empty_url(self):
        tool = WebFetchTool()
        result = await tool.run(url="")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_rejects_ftp_scheme(self):
        tool = WebFetchTool()
        result = await tool.run(url="ftp://example.com/file")
        assert "Error" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_get(self):
        respx.get("https://example.com/api").mock(
            return_value=httpx.Response(
                200,
                content=b'{"hello": "world"}',
                headers={"content-type": "application/json"},
            )
        )
        tool = WebFetchTool()
        result = await tool.run(url="https://example.com/api")
        assert "200" in result
        assert '"hello": "world"' in result
        assert "application/json" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_404(self):
        respx.get("https://example.com/missing").mock(
            return_value=httpx.Response(404, text="not found")
        )
        tool = WebFetchTool()
        result = await tool.run(url="https://example.com/missing")
        assert "404" in result
        assert "Error" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_timeout(self):
        respx.get("https://slow.example.com").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        tool = WebFetchTool()
        result = await tool.run(url="https://slow.example.com", timeout_s=1.0)
        assert "timeout" in result.lower()
        assert "Error" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_truncates_large_response(self):
        huge = b"x" * (100 * 1024)  # 100 KB
        respx.get("https://big.example.com").mock(
            return_value=httpx.Response(200, content=huge)
        )
        tool = WebFetchTool()
        result = await tool.run(url="https://big.example.com", max_chars=1024)
        assert "truncated" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_clamps_max_chars_to_safe_range(self):
        respx.get("https://example.com").mock(
            return_value=httpx.Response(200, content=b"x" * 100)
        )
        tool = WebFetchTool()
        result1 = await tool.run(url="https://example.com", max_chars=10)
        result2 = await tool.run(url="https://example.com", max_chars=10**9)
        assert "Error" not in result1
        assert "Error" not in result2


# ---------------------------------------------------------------------------
# WeatherTool
# ---------------------------------------------------------------------------


def _wttr_payload(
    city="Hong Kong",
    region="Hong Kong",
    country="Hong Kong",
    desc="Partly cloudy",
    temp_c="28",
    feels_c="32",
    humidity="70",
    wind_kmph="12",
    wind_dir="S",
    high="31",
    low="25",
    sunrise="06:15 AM",
    sunset="06:45 PM",
) -> dict:
    return {
        "current_condition": [
            {
                "temp_C": temp_c,
                "FeelsLikeC": feels_c,
                "humidity": humidity,
                "windspeedKmph": wind_kmph,
                "winddir16Point": wind_dir,
                "weatherDesc": [{"value": desc}],
                "observation_time": "02:00 PM",
            }
        ],
        "nearest_area": [
            {
                "areaName": [{"value": city}],
                "region": [{"value": region}],
                "country": [{"value": country}],
            }
        ],
        "weather": [
            {
                "maxtempC": high,
                "mintempC": low,
                "astronomy": [{"sunrise": sunrise, "sunset": sunset}],
            }
        ],
    }


class TestWeatherTool:
    def test_schema(self):
        tool = WeatherTool()
        assert tool.name == "weather"
        assert "location" in tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_rejects_empty_location(self):
        tool = WeatherTool()
        result = await tool.run(location="")
        assert "Error" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_lookup(self):
        respx.get("https://wttr.in/Hong%20Kong").mock(
            return_value=httpx.Response(
                200,
                content=json.dumps(_wttr_payload()).encode(),
                headers={"content-type": "application/json"},
            )
        )
        tool = WeatherTool()
        result = await tool.run(location="Hong Kong")
        assert "Hong Kong" in result
        assert "28" in result
        assert "Partly cloudy" in result
        assert "70%" in result
        assert "wttr.in" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_airport_code(self):
        respx.get("https://wttr.in/HKG").mock(
            return_value=httpx.Response(
                200,
                content=json.dumps(_wttr_payload(city="HKG")).encode(),
            )
        )
        tool = WeatherTool()
        result = await tool.run(location="HKG")
        assert "HKG" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_404(self):
        respx.get("https://wttr.in/NonsenseLocation").mock(
            return_value=httpx.Response(404, text="not found")
        )
        tool = WeatherTool()
        result = await tool.run(location="NonsenseLocation")
        assert "Error" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_timeout(self):
        respx.get("https://wttr.in/Slow").mock(
            side_effect=httpx.TimeoutException("slow")
        )
        tool = WeatherTool()
        result = await tool.run(location="Slow")
        assert "timed out" in result.lower()

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_non_json_response(self):
        respx.get("https://wttr.in/HTML").mock(
            return_value=httpx.Response(
                200,
                content=b"<html>oops</html>",
                headers={"content-type": "text/html"},
            )
        )
        tool = WeatherTool()
        result = await tool.run(location="HTML")
        assert "non-JSON" in result or "could not parse" in result

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_malformed_payload(self):
        respx.get("https://wttr.in/Bad").mock(
            return_value=httpx.Response(
                200,
                content=b'{"current_condition": []}',
            )
        )
        tool = WeatherTool()
        result = await tool.run(location="Bad")
        assert "could not parse" in result or "Location: ?" in result
