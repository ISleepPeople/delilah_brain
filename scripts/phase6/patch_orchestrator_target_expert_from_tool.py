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

    anchor = '                tool_name = state.get("tool") or (policy_tool if is_tool_intent else "weather")\n                state["tool"] = tool_name\n                trace_id = (state.get("trace_id") or "trace_missing").strip() or "trace_missing"\n'
    if anchor not in src:
        die("missing anchor in tooling block (unexpected orchestrator layout)")

    if "Phase 6.1: target_expert must follow tool_name for tool intents" in src:
        print("PATCH OK: target_expert override already present; no changes.")
        raise SystemExit(0)

    insert = (
        '                tool_name = state.get("tool") or (policy_tool if is_tool_intent else "weather")\n'
        '                state["tool"] = tool_name\n'
        '                # Phase 6.1: target_expert must follow tool_name for tool intents (prevents router_hint bleed-through)\n'
        '                if tool_name == "weather":\n'
        '                    state["target_expert"] = "weather"\n'
        '                elif isinstance(tool_name, str) and tool_name.startswith("system."):\n'
        '                    state["target_expert"] = "system"\n'
        '                elif isinstance(tool_name, str) and tool_name.startswith("mqtt."):\n'
        '                    state["target_expert"] = "mqtt"\n'
        '                else:\n'
        '                    state["target_expert"] = state.get("target_expert") or "general"\n'
        '                trace_id = (state.get("trace_id") or "trace_missing").strip() or "trace_missing"\n'
    )

    new_src = src.replace(anchor, insert, 1)

    tmp = ORCH.with_suffix(".py.new")
    tmp.write_text(new_src)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"orchestrator.py.pre_target_expert_from_tool.{ts}.bak"
    backup.write_text(src)

    ORCH.write_text(new_src)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: orchestrator now sets target_expert from tool_name for tool intents (backup: {backup})")

if __name__ == "__main__":
    main()
