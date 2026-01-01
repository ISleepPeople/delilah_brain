from __future__ import annotations

from pathlib import Path
import time
import py_compile
import sys
import re

ORCH = Path("/home/dad/delilah_workspace/orchestrator.py")
BACKUP_DIR = Path("/home/dad/delilah_workspace/backups/phase6")

def die(msg: str) -> None:
    print(f"PATCH ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)

def main() -> None:
    if not ORCH.exists():
        die(f"missing {ORCH}")

    src = ORCH.read_text(errors="replace")

    # Anchor: we know there is a policy call producing `policy_intent` / `policy_tool_name` in state.
    if 'state["policy_intent"]' not in src or 'state["policy_tool_name"]' not in src:
        die("missing anchors: state['policy_intent'] / state['policy_tool_name']")

    # Anchor: ToolExecutor exists in this file (already wired for weather).
    if "ToolExecutor" not in src or "executor.execute" not in src:
        die("missing ToolExecutor wiring in orchestrator (unexpected)")

    # Insert a generic tool-intent execution block immediately AFTER policy is computed,
    # and BEFORE any RAG/LLM flow begins.
    # We anchor on the first occurrence of setting policy_intent/tool_name, then insert after that cluster.
    m = re.search(r'state\["policy_tool_name"\]\s*=\s*.*\n', src)
    if not m:
        die("could not locate policy_tool_name assignment line")

    insert_at = m.end()

    # Avoid duplicate insertion
    if "Generic tool intent execution (Tool APIs v1)" in src:
        print("PATCH OK: generic tool intent execution already present; no changes.")
        raise SystemExit(0)

    block = r'''
        # Generic tool intent execution (Tool APIs v1)
        # If policy decided this is a tool intent, execute tool via centralized executor and hard-stop (no RAG/LLM fallback).
        if state.get("policy_intent") == "tool" and state.get("policy_tool_name"):
            tool_name = state["policy_tool_name"]
            state["tool"] = tool_name

            # Build minimal args for known Tool APIs v1
            tool_args = {}
            if tool_name == "weather":
                # existing helper populates location_name/coordinates when present
                tool_args = parse_weather_args(text) or {}
            elif tool_name == "system.health_check":
                tool_args = {}
            elif tool_name == "system.get_versions":
                tool_args = {}
            elif tool_name == "mqtt.publish":
                # Conservative parse: requires explicit topic in text.
                # Accept: "topic: x/y payload: hello" or "topic x/y payload hello"
                import re as _re
                t = text or ""
                mt = _re.search(r'(?:topic\s*:?\s*)([A-Za-z0-9_\-\/\.]+)', t, flags=_re.IGNORECASE)
                mp = _re.search(r'(?:payload\s*:?\s*)(.+)$', t, flags=_re.IGNORECASE)
                if mt:
                    tool_args["topic"] = mt.group(1)
                if mp:
                    tool_args["payload"] = mp.group(1).strip()
            else:
                # Unknown tool (defensive) => treat as denied
                state["tool_result"] = {"ok": False, "error": f"unknown tool: {tool_name}", "result": {"tool": tool_name}}
                state["answer"] = f"Tool denied: unknown tool '{tool_name}'."
                state["source"] = "tool_error"
                state["used_context"] = False
                state["num_docs"] = 0
                state["used_conversation_context"] = False
                return state

            state["tool_args"] = tool_args

            # Execute via centralized executor
            try:
                tr = executor.execute(tool_name, tool_args, trace_id=state.get("trace_id"))
            except Exception as e:
                tr = {"ok": False, "error": f"tool executor exception: {type(e).__name__}: {e}", "result": {"tool": tool_name}}

            state["tool_result"] = tr

            # Deterministic tool success
            if (tr or {}).get("ok") is True:
                rr = (tr or {}).get("result") or {}
                if tool_name == "weather":
                    loc = rr.get("location") or tool_args.get("location") or ""
                    summ = (rr.get("summary") or "").strip()
                    state["answer"] = f"{loc}: {summ}" if loc else summ
                elif tool_name == "system.health_check":
                    state["answer"] = rr.get("summary") or "system.health_check OK"
                elif tool_name == "system.get_versions":
                    state["answer"] = rr.get("summary") or "system.get_versions OK"
                elif tool_name == "mqtt.publish":
                    state["answer"] = rr.get("summary") or "mqtt.publish OK"
                else:
                    state["answer"] = rr.get("summary") or f"{tool_name} OK"

                state["source"] = "tool"
                state["used_context"] = False
                state["num_docs"] = 0
                state["used_conversation_context"] = False
                return state

            # Deterministic tool failure (hard-stop; prevents hallucinations)
            rr = (tr or {}).get("result") or {}
            err = (tr or {}).get("error") or rr.get("error") or "tool failed"
            state["answer"] = f"{tool_name} failed: {err}"
            state["source"] = "tool_error"
            state["used_context"] = False
            state["num_docs"] = 0
            state["used_conversation_context"] = False
            return state
'''

    new_src = src[:insert_at] + block + src[insert_at:]

    tmp = ORCH.with_suffix(".py.new")
    tmp.write_text(new_src)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"orchestrator.py.pre_generic_tool_intents_v1.{ts}.bak"
    backup.write_text(src)

    ORCH.write_text(new_src)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: orchestrator now executes policy tool intents generically (backup: {backup})")

if __name__ == "__main__":
    main()
