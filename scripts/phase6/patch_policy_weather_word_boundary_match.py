from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import re

ROOT = Path("/home/dad/delilah_workspace")
POL = ROOT / "policy" / "policy.py"
BKP_DIR = ROOT / "backups" / "phase6"
BKP_DIR.mkdir(parents=True, exist_ok=True)

STAMP = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
BACKUP = BKP_DIR / f"policy.py.pre_weather_word_boundary.{STAMP}.bak"

OLD_BLOCK = """    if any(w in t for w in _WEATHER_WORDS):
        return "weather"
"""

NEW_BLOCK = """    # Weather tool (match whole words only; avoid false positives like "brain" -> "rain")
    if re.search(r"\\b(?:weather|forecast|temperature|rain|snow|wind)\\b", t, flags=re.IGNORECASE):
        return "weather"
"""

def main() -> None:
    src = POL.read_text(encoding="utf-8")

    if "def classify_tool_name" not in src:
        raise SystemExit("PATCH ERROR: classify_tool_name not found in policy/policy.py")

    # Ensure `import re` exists (idempotent)
    if re.search(r"^import re\\s*$", src, flags=re.M) is None and re.search(r"^from .* import re\\b", src, flags=re.M) is None:
        # Insert after the last stdlib import line near top (best-effort, safe)
        lines = src.splitlines(True)
        insert_at = 0
        for i, ln in enumerate(lines[:60]):
            if ln.startswith("import ") or ln.startswith("from "):
                insert_at = i + 1
        lines.insert(insert_at, "import re\n")
        src = "".join(lines)

    if OLD_BLOCK not in src:
        # If already patched, do a quick self-test and exit cleanly
        if "avoid false positives like \"brain\" -> \"rain\"" in src:
            print("PATCH SKIP: weather word-boundary match already present.")
        else:
            raise SystemExit("PATCH ERROR: expected weather substring block not found; anchors changed.")
    else:
        BACKUP.write_text(src, encoding="utf-8")
        src2 = src.replace(OLD_BLOCK, NEW_BLOCK)
        POL.write_text(src2, encoding="utf-8")
        print(f"PATCH OK: weather detection now uses word boundaries (backup: {BACKUP})")

    # Self-test in-process by importing the updated module
    import importlib.util
    spec = importlib.util.spec_from_file_location("pol", str(POL))
    pol = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pol)

    tests = {
        "mqtt publish topic: delilah/test payload: hello-from-env-brain": "mqtt.publish",
        "weather San Juan, PR": "weather",
        "my brain hurts": None,
        "rain tomorrow": "weather",
    }
    for txt, expected in tests.items():
        got = pol.classify_tool_name(txt)
        if got != expected:
            raise SystemExit(f"SELFTEST FAIL: {txt!r} => {got!r}, expected {expected!r}")

    print("SELFTEST OK: classify_tool_name behavior verified")

if __name__ == "__main__":
    main()
