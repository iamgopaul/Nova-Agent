from __future__ import annotations

import asyncio
import urllib.parse

import httpx

from nova.tools.base import BaseTool, ToolResult


class WeatherTool(BaseTool):
    name = "get_weather"
    description = (
        "Get the current real-time weather for any location. "
        "Returns temperature (°F and °C), conditions, humidity, wind speed, and a 3-day forecast. "
        "Use this for any weather, temperature, rain, or forecast question."
    )

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City and state or country, e.g. 'Homestead, FL' or 'London, UK'.",
                    }
                },
                "required": ["location"],
            }
        )

    async def run(self, location: str = "") -> ToolResult:
        # When no location is given, omit the path segment — wttr.in will
        # auto-detect from the outgoing IP address (user's machine when running locally).
        encoded = urllib.parse.quote(location.strip()) if location.strip() else ""
        url = f"https://wttr.in/{encoded}?format=j1"

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                r = await client.get(url, headers={"User-Agent": "Nova-Agent/1.0"})
                r.raise_for_status()
                data = r.json()
        except Exception as exc:
            return ToolResult(content=f"Weather unavailable: {exc}", error=str(exc))

        try:
            curr = data["current_condition"][0]
            temp_f = curr["temp_F"]
            temp_c = curr["temp_C"]
            feels_f = curr["FeelsLikeF"]
            condition = curr["weatherDesc"][0]["value"]
            humidity = curr["humidity"]
            wind_mph = curr["windspeedMiles"]

            # Resolve display location: prefer the returned area name over the query.
            area = (data.get("nearest_area") or [{}])[0]
            city   = (area.get("areaName") or [{}])[0].get("value", "")
            region = (area.get("region")   or [{}])[0].get("value", "")
            display_loc = ", ".join(p for p in [city, region] if p) or location or "your location"

            today = data["weather"][0]
            max_f = today["maxtempF"]
            min_f = today["mintempF"]
            hourly = today.get("hourly", [])
            rain_chance = max(int(h.get("chanceofrain", 0)) for h in hourly) if hourly else 0

            tomorrow = data["weather"][1] if len(data["weather"]) > 1 else None
            tomorrow_desc = ""
            if tomorrow:
                t_cond = ""
                if tomorrow.get("hourly") and len(tomorrow["hourly"]) > 4:
                    t_cond = tomorrow["hourly"][4]["weatherDesc"][0]["value"]
                t_max = tomorrow["maxtempF"]
                t_min = tomorrow["mintempF"]
                tomorrow_desc = f"\nTomorrow: {t_cond}, {t_min}–{t_max}°F" if t_cond else f"\nTomorrow: {t_min}–{t_max}°F"

            summary = (
                f"Current weather in {display_loc}:\n"
                f"  {condition}, {temp_f}°F ({temp_c}°C) — feels like {feels_f}°F\n"
                f"  Today's range: {min_f}–{max_f}°F\n"
                f"  Rain chance: {rain_chance}%  |  Humidity: {humidity}%  |  Wind: {wind_mph} mph"
                f"{tomorrow_desc}"
            )
            return ToolResult(content=summary)
        except (KeyError, IndexError) as exc:
            return ToolResult(content=f"Could not parse weather data: {exc}", error=str(exc))
