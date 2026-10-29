"""Tool: weather lookup via Open-Meteo (free, no API key, no rate limits)."""
from functools import lru_cache

import requests
from langchain_core.tools import tool

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo's WMO weather codes -> human readable
WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains",
    80: "light rain showers", 81: "rain showers", 82: "violent rain showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}


@lru_cache(maxsize=128)
def _geocode(location: str) -> tuple[float, float, str] | None:
    """Resolve a location name to (lat, lon, display_name). Cached."""
    try:
        r = requests.get(
            GEOCODE_URL,
            params={"name": location, "count": 1, "format": "json"},
            timeout=5,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None
        loc = results[0]
        display = ", ".join(
            x for x in [loc.get("name"), loc.get("admin1"), loc.get("country")] if x
        )
        return loc["latitude"], loc["longitude"], display
    except requests.RequestException:
        return None


@tool
def weather(location: str, units: str = "metric") -> str:
    """Get current weather and a 3-day forecast for any location.

    Args:
        location: A city name (e.g. "Karachi", "London", "Tokyo"), optionally
            with country (e.g. "Paris, France").
        units: "metric" for Celsius/km/h or "imperial" for Fahrenheit/mph.
            Default: metric.

    Returns:
        A concise summary of current conditions and the next 3 days.
    """
    geo = _geocode(location)
    if not geo:
        return f"Error: could not find location {location!r}."

    lat, lon, display = geo
    is_imperial = units.lower().startswith("imp") or units.lower() == "us"
    temp_unit = "fahrenheit" if is_imperial else "celsius"
    wind_unit = "mph" if is_imperial else "kmh"
    temp_sym = "°F" if is_imperial else "°C"
    wind_sym = "mph" if is_imperial else "km/h"

    try:
        r = requests.get(
            WEATHER_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                "temperature_unit": temp_unit,
                "wind_speed_unit": wind_unit,
                "timezone": "auto",
                "forecast_days": 4,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        return f"Error: weather API unavailable: {e}"

    current = data.get("current", {})
    daily = data.get("daily", {})

    cur_temp = current.get("temperature_2m", "?")
    cur_humidity = current.get("relative_humidity_2m", "?")
    cur_wind = current.get("wind_speed_10m", "?")
    cur_desc = WEATHER_CODES.get(current.get("weather_code", -1), "unknown")

    lines = [
        f"Weather in {display}:",
        f"  Now: {cur_temp}{temp_sym}, {cur_desc}, "
        f"humidity {cur_humidity}%, wind {cur_wind} {wind_sym}",
        "  Forecast:",
    ]

    dates = daily.get("time", [])
    codes = daily.get("weather_code", [])
    highs = daily.get("temperature_2m_max", [])
    lows = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_sum", [])
    # Skip today's slot at index 0; show the next 3 days.
    for i in range(1, min(4, len(dates))):
        desc = WEATHER_CODES.get(codes[i] if i < len(codes) else -1, "?")
        hi = highs[i] if i < len(highs) else "?"
        lo = lows[i] if i < len(lows) else "?"
        rain = precip[i] if i < len(precip) else 0
        rain_str = f", {rain}mm precip" if rain and rain > 0 else ""
        lines.append(f"    {dates[i]}: {desc}, {lo}–{hi}{temp_sym}{rain_str}")

    return "\n".join(lines)
