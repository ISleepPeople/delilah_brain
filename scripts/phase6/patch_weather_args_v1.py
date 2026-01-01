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

def main() -> None:
    if not ORCH.exists():
        die(f"missing {ORCH}")

    src = ORCH.read_text(errors="replace")

    # Locate the existing parse_weather_args() function regardless of exact spacing.
    pat = re.compile(
        r"^def\s+parse_weather_args\(\s*query_text\s*:\s*str\s*\)\s*->\s*Dict\s*\[\s*str\s*,\s*Any\s*\]\s*:\s*\n"
        r"(?:^[ \t].*\n)+",
        flags=re.MULTILINE,
    )
    m = pat.search(src)
    if not m:
        die("could not find parse_weather_args(query_text: str) -> Dict[str, Any]")

    replacement = (
        "def parse_weather_args(query_text: str) -> Dict[str, Any]:\n"
        "    \"\"\"Extract a location from common weather/forecast phrasings.\n"
        "    Returns {} if no location is confidently found (caller may fall back).\n"
        "    \"\"\"\n"
        "    t = (query_text or \"\").strip()\n"
        "    if not t:\n"
        "        return {}\n"
        "\n"
        "    # Prefer matching 'weather/forecast ... in/for <location>'\n"
        "    rx = re.compile(\n"
        "        r\"\\b(?:weather|forecast)\\b\"\n"
        "        r\"(?:\\s+(?:today|tonight|tomorrow|right\\s+now|this\\s+week|this\\s+weekend))?\"\n"
        "        r\"\\s+(?:in|for)\\s+(?P<loc>.+?)\"\n"
        "        r\"(?:[\\?\\.!]\\s*|\\s*$)\",\n"
        "        flags=re.IGNORECASE,\n"
        "    )\n"
        "    m = rx.search(t)\n"
        "\n"
        "    # Secondary fallback: allow 'in/for <location>' even without the word 'weather'\n"
        "    if not m:\n"
        "        rx2 = re.compile(\n"
        "            r\"\\b(?:in|for)\\s+(?P<loc>[^\\?\\.!]+?)(?:[\\?\\.!]\\s*|\\s*$)\",\n"
        "            flags=re.IGNORECASE,\n"
        "        )\n"
        "        m = rx2.search(t)\n"
        "        if not m:\n"
        "            return {}\n"
        "\n"
        "    loc = (m.group(\"loc\") or \"\").strip()\n"
        "    loc = re.sub(r\"\\s+(?:please|thanks|thank\\s+you)\\s*$\", \"\", loc, flags=re.IGNORECASE).strip()\n"
        "    loc = loc.strip('\"\\'').strip()\n"
        "\n"
        "    # Keep compatibility with weather_tool() which checks location OR location_name\n"
        "    return {\"location\": loc}\n"
    )

    out = src[:m.start()] + replacement + src[m.end():]

    # Write .new and compile-check before swapping live file
    tmp = REPO / "orchestrator.py.new"
    tmp.write_text(out)
    py_compile.compile(str(tmp), doraise=True)

    # Backup original
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"orchestrator.py.pre_weather_args_v1.{ts}.bak"
    backup.write_text(src)

    # Apply
    ORCH.write_text(out)

    print(f"PATCH OK: parse_weather_args hardened (backup: {backup})")

if __name__ == "__main__":
    main()
