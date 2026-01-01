from __future__ import annotations

from pathlib import Path
import time
import py_compile
import sys

FILE = Path("/home/dad/delilah_workspace/policy/policy.py")
BACKUP_DIR = Path("/home/dad/delilah_workspace/backups/phase6")

def die(msg: str) -> None:
    print(f"PATCH ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)

def main() -> None:
    if not FILE.exists():
        die(f"missing {FILE}")

    src = FILE.read_text(errors="replace")

    # Anchors from the current file (v0 weather-only policy).
    if "_WEATHER_WORDS = (" not in src:
        die("missing anchor: _WEATHER_WORDS")
    if "def classify_intent(text: str) -> Intent:" not in src:
        die("missing anchor: classify_intent")
    if "def decide_routing(text: str) -> RoutingPlan:" not in src:
        die("missing anchor: decide_routing")

    if "def classify_tool_name(text: str)" in src:
        print("PATCH OK: policy already has classify_tool_name(); no changes.")
        raise SystemExit(0)

    insert_after = '_TIME_VOLATILE_WORDS = ("today", "tonight", "right now", "current", "latest", "score", "prices", "stock", "stocks")\n\n'
    if insert_after not in src:
        die("missing anchor: _TIME_VOLATILE_WORDS block (unexpected policy layout)")

    tool_name_fn = '''# Tool name classifier (Tool APIs v1)
# Note: we keep this deterministic and conservative to avoid side-effects.
def classify_tool_name(text: str) -> Optional[str]:
    t = (text or "").lower()

    # Weather tool
    if any(w in t for w in _WEATHER_WORDS):
        return "weather"

    # System tools
    # - "health check" / "status" => system.health_check
    # - "versions" / "what versions" => system.get_versions
    if any(p in t for p in ["health check", "healthcheck", "system status", "service status", "status check", "uptime"]):
        return "system.health_check"
    if any(p in t for p in ["what version", "versions", "version info", "build info", "what are you running"]):
        return "system.get_versions"

    # MQTT publish tool (only if user explicitly mentions topic to avoid unintended publishes)
    if "mqtt" in t and ("topic " in t or "topic:" in t):
        return "mqtt.publish"
    if "publish" in t and ("topic " in t or "topic:" in t):
        return "mqtt.publish"

    return None

'''

    src = src.replace(insert_after, insert_after + tool_name_fn)

    # Replace classify_intent: tool iff a tool name is detected.
    old_classify_intent = '''def classify_intent(text: str) -> Intent:
    t = (text or "").lower()
    # v0: only weather is a tool intent in the baseline
    if any(w in t for w in _WEATHER_WORDS):
        return Intent.TOOL
    return Intent.KNOWLEDGE
'''
    if old_classify_intent not in src:
        die("classify_intent block does not match expected v0 text; aborting to avoid a bad patch")

    new_classify_intent = '''def classify_intent(text: str) -> Intent:
    # Tool intent iff we can deterministically name the tool.
    return Intent.TOOL if classify_tool_name(text) else Intent.KNOWLEDGE
'''
    src = src.replace(old_classify_intent, new_classify_intent)

    # Replace classify_volatility: any tool intent is volatile (ephemeral / real-time / stateful)
    old_classify_vol = '''def classify_volatility(text: str) -> Volatility:
    t = (text or "").lower()
    # v0: weather + explicit time-sensitive phrasing are volatile
    if any(w in t for w in _WEATHER_WORDS):
        return Volatility.VOLATILE
    if any(w in t for w in _TIME_VOLATILE_WORDS):
        return Volatility.VOLATILE
    return Volatility.STABLE
'''
    if old_classify_vol not in src:
        die("classify_volatility block does not match expected v0 text; aborting to avoid a bad patch")

    new_classify_vol = '''def classify_volatility(text: str) -> Volatility:
    t = (text or "").lower()
    # Any tool intent is treated as volatile (no writeback).
    if classify_tool_name(text):
        return Volatility.VOLATILE
    if any(w in t for w in _TIME_VOLATILE_WORDS):
        return Volatility.VOLATILE
    return Volatility.STABLE
'''
    src = src.replace(old_classify_vol, new_classify_vol)

    # Replace decide_routing: select tool_name deterministically.
    old_decide_routing = '''def decide_routing(text: str) -> RoutingPlan:
    intent = classify_intent(text)
    vol = classify_volatility(text)

    if intent == Intent.TOOL:
        # v0: route weather to tool layer; expert remains "general" for now
        return RoutingPlan(intent=intent, volatility=vol, expert_id="general", tool_name="weather")

    return RoutingPlan(intent=intent, volatility=vol, expert_id="general", tool_name=None)
'''
    if old_decide_routing not in src:
        die("decide_routing block does not match expected v0 text; aborting to avoid a bad patch")

    new_decide_routing = '''def decide_routing(text: str) -> RoutingPlan:
    intent = classify_intent(text)
    vol = classify_volatility(text)

    if intent == Intent.TOOL:
        tool = classify_tool_name(text)
        if not tool:
            # Defensive: should not happen because classify_intent depends on tool_name.
            return RoutingPlan(intent=Intent.KNOWLEDGE, volatility=vol, expert_id="general", tool_name=None)
        return RoutingPlan(intent=intent, volatility=vol, expert_id="general", tool_name=tool)

    return RoutingPlan(intent=intent, volatility=vol, expert_id="general", tool_name=None)
'''
    src = src.replace(old_decide_routing, new_decide_routing)

    # Compile-check before writing
    tmp = FILE.with_suffix(".py.new")
    tmp.write_text(src)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"policy.py.pre_tool_apis_v1.{ts}.bak"
    backup.write_text(FILE.read_text(errors="replace"))

    FILE.write_text(src)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: policy tool routing now supports system.* and mqtt.publish (backup: {backup})")

if __name__ == "__main__":
    main()
