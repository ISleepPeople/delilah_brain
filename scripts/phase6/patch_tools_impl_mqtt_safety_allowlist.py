from __future__ import annotations

from pathlib import Path
import time
import py_compile
import sys

FILE = Path("/home/dad/delilah_workspace/tools/impl_mqtt.py")
BACKUP_DIR = Path("/home/dad/delilah_workspace/backups/phase6")

def die(msg: str) -> None:
    print(f"PATCH ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)

def main() -> None:
    if not FILE.exists():
        die(f"missing {FILE}")

    src = FILE.read_text(errors="replace")

    # Anchor on the current function signature and current default host line.
    if "def mqtt_publish(args: Dict[str, Any]) -> Dict[str, Any]:" not in src:
        die("missing anchor: mqtt_publish()")
    if 'host = os.environ.get("MQTT_HOST", "127.0.0.1")' not in src:
        die('missing anchor: MQTT_HOST default "127.0.0.1" (file differs)')

    if "MUTATING_TOOLS_ENABLED" in src and "MQTT_ALLOW_PREFIXES" in src:
        print("PATCH OK: mqtt safety gates already present; no changes.")
        raise SystemExit(0)

    # Insert helpers near the top (after imports)
    insert_point = src.find("try:\n    import paho.mqtt.client as mqtt")
    if insert_point == -1:
        die("could not find insert point near paho-mqtt import")

    helpers = '''
def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return default


def _parse_prefixes(v: str) -> list[str]:
    parts = [p.strip() for p in (v or "").split(",")]
    return [p for p in parts if p]


def _topic_allowed(topic: str, prefixes: list[str]) -> bool:
    if not topic or not prefixes:
        return False
    return any(topic.startswith(p) for p in prefixes)
'''
    src = src[:insert_point] + helpers + "\n" + src[insert_point:]

    # Replace the mqtt_publish body in a minimally invasive way:
    # - add mutation gate
    # - add dry-run default
    # - add allowlist
    # - change default host to "mqtt"
    # We patch by inserting logic right after args validation.
    needle = '    if not topic or payload is None:\n        return {"ok": False, "error": "Missing required args: topic, payload"}\n\n'
    if needle not in src:
        die("missing anchor: args validation block (unexpected)")

    safety_block = '''    # --- Safety gates (Phase 6.1) ---
    # Mutating tools must be explicitly enabled.
    if not _env_bool("MUTATING_TOOLS_ENABLED", default=False):
        return {"ok": False, "error": "mqtt.publish denied: MUTATING_TOOLS_ENABLED is false"}

    # Dry-run by default unless explicitly overridden by args or env.
    dry_run_default = _env_bool("DRY_RUN_DEFAULT_FOR_MUTATIONS", default=True)
    dry_run = bool((args or {}).get("dry_run", dry_run_default))
    # Require an allowlist of topic prefixes. If not configured, deny publishes.
    allow_prefixes = _parse_prefixes(os.environ.get("MQTT_ALLOW_PREFIXES", ""))
    if not _topic_allowed(str(topic), allow_prefixes):
        return {"ok": False, "error": f"mqtt.publish denied: topic '{topic}' not allowed", "allowed_prefixes": allow_prefixes}

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "topic": topic,
            "payload": str(payload),
            "qos": qos,
            "retain": retain,
            "summary": f"DRY_RUN mqtt.publish to {topic} (qos={qos}, retain={retain})",
        }

'''
    src = src.replace(needle, needle + safety_block, 1)

    # Change default MQTT_HOST
    src = src.replace(
        'host = os.environ.get("MQTT_HOST", "127.0.0.1")',
        'host = os.environ.get("MQTT_HOST", "mqtt")',
        1
    )

    # Add summary field to success return (so orchestrator can print deterministic text)
    if '"ok": True,' in src and '"summary"' not in src:
        src = src.replace(
            '"ok": True,',
            '"ok": True,\n        "summary": f"mqtt.publish OK to {topic} (qos={qos}, retain={retain})",',
            1
        )

    tmp = FILE.with_suffix(".py.new")
    tmp.write_text(src)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"impl_mqtt.py.pre_safety_allowlist.{ts}.bak"
    backup.write_text(FILE.read_text(errors="replace"))

    FILE.write_text(src)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: impl_mqtt now enforces mutation gates + allowlist + dry-run default (backup: {backup})")

if __name__ == "__main__":
    main()
