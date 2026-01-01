"""
Weather tool implementation (Phase 6.1).

Canonical tool name: "weather"

Args:
  - location (preferred) or location_name
If omitted, caller may supply a default location upstream.
"""

from __future__ import annotations

from typing import Any, Dict


def weather_tool(tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Real-time weather lookup using weather.gov.

    Policy:
      - No RAG context
      - No persistence to Postgres
      - No memory writes
    """
    import requests
    import time

    location_query = (
        (tool_args or {}).get("location")
        or (tool_args or {}).get("location_name")
        or ""
    ).strip()

    if not location_query:
        return {"ok": False, "error": "Missing location", "source": "weather.gov"}

    headers = {
        "User-Agent": "Delilah/1.0 (contact: local)",
        "Accept": "application/geo+json, application/json;q=0.9, */*;q=0.1",
    }

    session = requests.Session()
    session.headers.update(headers)

    def _get_json(url: str, *, params: Dict[str, Any] | None = None, timeout: int = 15, retries: int = 2) -> Any:
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = session.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(0.8)
        raise last_err  # type: ignore[misc]

    try:
        geo = _get_json(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location_query, "format": "json", "limit": 1},
            timeout=15,
            retries=2,
        )

        if not geo:
            return {"ok": False, "error": f"Could not resolve location {location_query}", "source": "weather.gov"}

        lat = geo[0]["lat"]
        lon = geo[0]["lon"]

        points = _get_json(
            f"https://api.weather.gov/points/{lat},{lon}",
            timeout=15,
            retries=2,
        )

        forecast_url = points["properties"]["forecast"]

        forecast = _get_json(
            forecast_url,
            timeout=15,
            retries=2,
        )

        periods = forecast["properties"]["periods"]
        if not periods:
            return {"ok": False, "error": "Weather forecast unavailable", "source": "weather.gov"}

        now = periods[0]
        summary = f"{now['name']}: {now['temperature']} {now['temperatureUnit']}, {now['shortForecast']}."

        return {
            "ok": True,
            "location": location_query,
            "summary": summary,
            "source": "weather.gov",
            "used_context": False,
        }

    except Exception as e:
        return {"ok": False, "error": str(e), "source": "weather.gov"}
