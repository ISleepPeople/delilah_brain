from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/home/dad/delilah_workspace")
ORCH = ROOT / "orchestrator.py"
BKP_DIR = ROOT / "backups" / "phase6"
BKP_DIR.mkdir(parents=True, exist_ok=True)

STAMP = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
BACKUP = BKP_DIR / f"orchestrator.py.pre_weather_args_fallback_parse.{STAMP}.bak"

INSERT_COMMENT = "# Phase 6.x: weather arg parsing fallback (handles shorthand like 'weather san juan pr')"

def main() -> None:
    src = ORCH.read_text()

    if "def parse_weather_args" not in src:
        raise SystemExit("ERROR: parse_weather_args() not found in orchestrator.py (unexpected).")

    if INSERT_COMMENT in src:
        print("PATCH SKIP: fallback already present.")
        return

    lines = src.splitlines(True)

    # We will insert inside the first weather tool request block:
    #   if tool_name == "weather":
    #       <INSERT HERE>
    #       if not state["tool_args"].get("location") ...
    weather_if_idx = None
    guard_idx = None

    for i, ln in enumerate(lines):
        if 'if tool_name == "weather":' in ln:
            weather_if_idx = i
            # search forward for the default-location guard
            for j in range(i + 1, min(i + 80, len(lines))):
                if 'if not state["tool_args"].get("location")' in lines[j] and 'location_name' in lines[j]:
                    guard_idx = j
                    break
            if guard_idx is not None:
                break

    if weather_if_idx is None or guard_idx is None:
        raise SystemExit(
            "ERROR: Could not locate weather tool block with default-location guard. "
            "Search anchors changed; safer to re-anchor with a new diagnostics snippet."
        )

    indent = lines[guard_idx].split("if", 1)[0]  # indentation of the guard line

    insert_block = (
        f"{indent}{INSERT_COMMENT}\n"
        f"{indent}if not state.get(\"tool_args\"):\n"
        f"{indent}    state[\"tool_args\"] = {{}}\n"
        f"{indent}if not state[\"tool_args\"].get(\"location\") and not state[\"tool_args\"].get(\"location_name\"):\n"
        f"{indent}    parsed = parse_weather_args(text)\n"
        f"{indent}    for k, v in (parsed or {{}}).items():\n"
        f"{indent}        if v and not state[\"tool_args\"].get(k):\n"
        f"{indent}            state[\"tool_args\"][k] = v\n"
    )

    # backup + write
    BACKUP.write_text(src)
    new_src = "".join(lines[:guard_idx] + [insert_block] + lines[guard_idx:])
    ORCH.write_text(new_src)

    print(f"PATCH OK: weather tool now backfills tool_args via parse_weather_args() (backup: {BACKUP})")

if __name__ == "__main__":
    main()
