from __future__ import annotations

from pathlib import Path
import re
import sys
import time
import py_compile

REPO = Path("/home/dad/delilah_workspace")
ORCH = REPO / "orchestrator.py"
BACKUP_DIR = REPO / "backups" / "phase6"

def die(msg: str) -> None:
    print(f"PATCH ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)

NEW_FUNC = """def weather_tool(tool_args: Dict[str, Any]) -> Dict[str, Any]:
    \"""
    Real-time weather lookup using weather.gov.
    Policy:
      - No RAG context
      - No persistence to Postgres
      - No memory writes
    \"""
    import requests
    import time

    location_query = (
        tool_args.get("location")
        or tool_args.get("location_name")
        or DEFAULT_LOCATION_QUERY
    )

    # NWS strongly prefers a descriptive User-Agent. Keep contact "local" per your existing convention.
    headers = {
        "User-Agent": "Delilah/1.0 (contact: local)",
        "Accept": "application/geo+json, application/json;q=0.9, */*;q=0.1",
    }

    session = requests.Session()
    session.headers.update(headers)

    def _get_json(url: str, *, params: dict | None = None, timeout: int = 15, retries: int = 2) -> dict:
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                r = session.get(url, params=params, timeout=timeout)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(0.8)
        raise last_err  # type: ignore[misc]

    try:
        # 1) Resolve location to lat/lon (Nominatim)
        geo = _get_json(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location_query, "format": "json", "limit": 1},
            timeout=15,
            retries=2,
        )

        if not geo:
            return {
                "ok": False,
                "error": f"Could not resolve location '{location_query}'",
                "source": "weather.gov",
            }

        lat = geo[0]["lat"]
        lon = geo[0]["lon"]

        # 2) Get weather.gov grid endpoint
        points = _get_json(
            f"https://api.weather.gov/points/{lat},{lon}",
            timeout=15,
            retries=2,
        )

        forecast_url = points["properties"]["forecast"]

        # 3) Get forecast
        forecast = _get_json(
            forecast_url,
            timeout=15,
            retries=2,
        )

        periods = forecast["properties"]["periods"]
        if not periods:
            return {
                "ok": False,
                "error": "Weather forecast unavailable",
                "source": "weather.gov",
            }

        now = periods[0]
        summary = (
            f"{now['name']}: {now['temperature']} {now['temperatureUnit']}, "
            f"{now['shortForecast']}."
        )

        return {
            "ok": True,
            "location": location_query,
            "summary": summary,
            "source": "weather.gov",
            "used_context": False,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "source": "weather.gov",
        }
"""

def main() -> None:
    if not ORCH.exists():
        die(f"missing {ORCH}")

    src = ORCH.read_text(errors="replace")

    # Verified structure: weather_tool() is followed by detect_weather_intent(). Replace the whole block.
    pat = re.compile(
        r"^def\s+weather_tool\(\s*tool_args:\s*Dict\s*\[\s*str\s*,\s*Any\s*\]\s*\)\s*->\s*Dict\s*\[\s*str\s*,\s*Any\s*\]\s*:\s*\n"
        r"(?:^[ \t].*\n)*?"
        r"(?=^def\s+detect_weather_intent\()",
        flags=re.MULTILINE,
    )
    m = pat.search(src)
    if not m:
        die("could not find weather_tool(...) block to replace (expected it immediately before detect_weather_intent)")

    out = src[:m.start()] + NEW_FUNC + "\n\n" + src[m.end():]

    # Write .new and compile-check before swapping
    tmp = REPO / "orchestrator.py.new"
    tmp.write_text(out)
    py_compile.compile(str(tmp), doraise=True)

    # Backup + apply
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"orchestrator.py.pre_weather_tool_http_v1.{ts}.bak"
    backup.write_text(src)

    ORCH.write_text(out)

    print(f"PATCH OK: weather_tool() HTTP hardened (backup: {backup})")

if __name__ == "__main__":
    main()
