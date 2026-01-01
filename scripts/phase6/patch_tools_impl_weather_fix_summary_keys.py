from __future__ import annotations

from pathlib import Path
import time
import py_compile
import sys

FILE = Path("/home/dad/delilah_workspace/tools/impl_weather.py")
BACKUP_DIR = Path("/home/dad/delilah_workspace/backups/phase6")

def die(msg: str) -> None:
    print(f"PATCH ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)

def main() -> None:
    if not FILE.exists():
        die(f"missing {FILE}")

    src = FILE.read_text(errors="replace")

    bad = 'summary = f"{now[name]}: {now[temperature]} {now[temperatureUnit]}, {now[shortForecast]}."\n'
    if bad not in src:
        die("missing exact anchor for bad summary line (file differs from expected)")

    good = 'summary = f"{now[\'name\']}: {now[\'temperature\']} {now[\'temperatureUnit\']}, {now[\'shortForecast\']}."\n'
    src2 = src.replace(bad, good, 1)

    tmp = FILE.with_suffix(".py.new")
    tmp.write_text(src2)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"impl_weather.py.pre_fix_summary_keys.{ts}.bak"
    backup.write_text(src)

    FILE.write_text(src2)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: fixed summary keys in tools/impl_weather.py (backup: {backup})")

if __name__ == "__main__":
    main()
