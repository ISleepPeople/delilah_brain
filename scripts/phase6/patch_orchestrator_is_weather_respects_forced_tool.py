from __future__ import annotations

from pathlib import Path
import time
import py_compile
import sys

ORCH = Path("/home/dad/delilah_workspace/orchestrator.py")
BACKUP_DIR = Path("/home/dad/delilah_workspace/backups/phase6")

def die(msg: str) -> None:
    print(f"PATCH ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)

def main() -> None:
    if not ORCH.exists():
        die(f"missing {ORCH}")

    src = ORCH.read_text(errors="replace")

    old = 'is_weather = detect_weather_intent(text)\n'
    if old not in src:
        # Allow for minor whitespace differences
        if "is_weather = detect_weather_intent(text)" not in src:
            die("missing anchor: is_weather = detect_weather_intent(text)")

    new = (
        '# Determine if this is an ephemeral tool intent (weather, etc.)\n'
        '# Policy may force tool execution even if the heuristic detector misses.\n'
        'is_weather = (state.get("tool") == "weather") or detect_weather_intent(text)\n'
    )

    if "Policy may force tool execution even if the heuristic detector misses." in src:
        print("PATCH OK: is_weather already respects forced tool; no changes.")
        raise SystemExit(0)

    src2 = src.replace(
        '# Determine if this is an ephemeral tool intent (weather, etc.)\n'
        'is_weather = detect_weather_intent(text)\n',
        new,
        1,
    )

    if src2 == src:
        # Fallback replace if comment header differs
        src2 = src.replace(old, new.splitlines()[-1] + "\n", 1)
        # But we still need the comment line; if we used fallback, keep it minimal.
        # If fallback happened, ensure we didn’t lose file integrity.
        if src2 == src:
            die("replace failed; orchestrator layout differs from expected anchors")

    tmp = ORCH.with_suffix(".py.new")
    tmp.write_text(src2)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"orchestrator.py.pre_is_weather_forced_tool.{ts}.bak"
    backup.write_text(src)

    ORCH.write_text(src2)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: is_weather now respects policy-forced tool (backup: {backup})")

if __name__ == "__main__":
    main()
