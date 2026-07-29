"""
skills/weather_skill.py — Current weather and short forecast via Open-Meteo.

Why this skill:
- Open-Meteo (open-meteo.com) is the consensus winner for free weather
  data in 2026: no API key, no signup, MIT-licensed Python SDK, 10K
  req/day free for non-commercial use, 30+ models, historical data
  from 1940.
- Pure stdlib `urllib` keeps the dependency surface zero.

How to call from a handler:
    from skills.weather_skill import weather
    text = await weather("Cairo", days=3)
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

UA = "Orca-Agent/0.6 (+https://github.com/hermasorca13-stack/Orca-Agent-Unified)"

# Open-Meteo geocoding + forecast endpoints. No key required.
_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FCST_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherError(RuntimeError):
    """Raised when weather lookup fails for any reason."""


def _http_json(url: str, params: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _geocode(place: str) -> Dict[str, Any]:
    data = _http_json(_GEO_URL, {"name": place, "count": 1, "language": "en", "format": "json"})
    results = data.get("results") or []
    if not results:
        raise WeatherError(f"Location not found: {place!r}")
    return results[0]


async def weather(place: str, days: int = 1) -> str:
    """Return a Markdown-friendly weather card for `place`.

    `days` may be 1..7. We always include the current snapshot plus the
    requested number of forecast days.
    """
    place = (place or "").strip()
    if not place:
        raise WeatherError("Empty location")
    days = max(1, min(7, int(days)))

    geo = _geocode(place)
    lat, lon = geo["latitude"], geo["longitude"]
    label = f"{geo['name']}, {geo.get('country', '')}".strip(", ")

    fc = _http_json(
        _FCST_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": days,
        },
    )

    cur = fc.get("current") or {}
    daily = fc.get("daily") or {}
    code_now: int = int(cur.get("weather_code", 0))
    desc_now = _WMO_CODE.get(code_now, f"code {code_now}")

    lines: List[str] = [f"🌦 *Weather — {label}*", ""]
    if cur:
        lines += [
            f"Now: *{cur.get('temperature_2m', '?')}°C*  ({desc_now})",
            f"Feels: {cur.get('apparent_temperature', '?')}°C  •  "
            f"Humidity {cur.get('relative_humidity_2m', '?')}%  •  "
            f"Wind {cur.get('wind_speed_10m', '?')} km/h",
        ]
    if daily and daily.get("time"):
        lines += ["", "*Forecast*"]
        for i, d in enumerate(daily["time"]):
            tmax = daily.get("temperature_2m_max", [None] * (i + 1))[i]
            tmin = daily.get("temperature_2m_min", [None] * (i + 1))[i]
            pop = daily.get("precipitation_probability_max", [None] * (i + 1))[i]
            code = int((daily.get("weather_code", [0] * (i + 1)) or [0] * (i + 1))[i] or 0)
            lines.append(
                f"  • {d}: {_WMO_CODE.get(code, '?')}  "
                f"{tmin}°/{tmax}°C  rain {pop if pop is not None else '?'}%"
            )
    return "\n".join(lines)


# Subset of the WMO weather interpretation codes. Source: open-meteo.com.
_WMO_CODE = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Heavy rain showers",
    82: "Violent rain showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm w/ light hail",
    99: "Thunderstorm w/ heavy hail",
}
