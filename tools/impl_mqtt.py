"""
MQTT tool implementations (Phase 6.1 Tool APIs v1).

mqtt.publish:
- Publishes a message to an MQTT broker.
- MUTATING tool (side effects).
- Requires env config for broker host/port and (optional) creds.

We keep the dependency footprint low by using paho-mqtt if installed.
If not installed, the tool returns a clear error so executor can report it.
"""

from __future__ import annotations

from typing import Any, Dict
import os
import time


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

try:
    import paho.mqtt.client as mqtt  # type: ignore
except Exception:
    mqtt = None  # noqa: N816


def mqtt_publish(args: Dict[str, Any]) -> Dict[str, Any]:
    if mqtt is None:
        return {"ok": False, "error": "paho-mqtt not installed"}

    topic = (args or {}).get("topic")
    payload = (args or {}).get("payload")
    qos = int((args or {}).get("qos", 0))
    retain = bool((args or {}).get("retain", False))

    if not topic or payload is None:
        return {"ok": False, "error": "Missing required args: topic, payload"}

    # --- Safety gates (Phase 6.1) ---
    # Mutating tools must be explicitly enabled.
    enable_mutations = _env_bool(
        "DELILAH_MQTT_ENABLE_MUTATIONS",
        default=_env_bool("MUTATING_TOOLS_ENABLED", default=False),
    )
    if not enable_mutations:
        return {
            "ok": False,
            "error": "mqtt.publish denied: mutations disabled (DELILAH_MQTT_ENABLE_MUTATIONS/MUTATING_TOOLS_ENABLED)",
        }

    # Dry-run by default unless explicitly overridden by args or env.
    dry_run_default = _env_bool(
        "DELILAH_MQTT_DRY_RUN",
        default=_env_bool("DRY_RUN_DEFAULT_FOR_MUTATIONS", default=True),
    )
    dry_run = bool((args or {}).get("dry_run", dry_run_default))

    # Require an allowlist of topic prefixes. If not configured, deny publishes.
    allow_prefixes = _parse_prefixes(
        os.environ.get("DELILAH_MQTT_ALLOWLIST", os.environ.get("MQTT_ALLOW_PREFIXES", ""))
    )
    if not _topic_allowed(str(topic), allow_prefixes):
        return {
            "ok": False,
            "error": f"mqtt.publish denied: topic '{topic}' not allowed",
            "allowed_prefixes": allow_prefixes,
        }

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

    host = os.environ.get("MQTT_HOST", "mqtt")
    port = int(os.environ.get("MQTT_PORT", "1883"))
    username = os.environ.get("MQTT_USERNAME")
    password = os.environ.get("MQTT_PASSWORD")

    client_id = f"delilah_brain_v2_{int(time.time())}"
    client = mqtt.Client(client_id=client_id, clean_session=True)

    if username:
        client.username_pw_set(username=username, password=password)

    # Connect + publish (blocking but short)
    client.connect(host, port, keepalive=20)
    info = client.publish(topic, payload=str(payload), qos=qos, retain=retain)
    info.wait_for_publish(timeout=5)
    client.disconnect()

    return {
        "ok": True,
        "host": host,
        "port": port,
        "topic": topic,
        "qos": qos,
        "retain": retain,
        "mid": getattr(info, "mid", None),
        "rc": getattr(info, "rc", None),
    }
