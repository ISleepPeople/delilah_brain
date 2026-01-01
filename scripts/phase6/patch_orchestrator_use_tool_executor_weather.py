from __future__ import annotations

from pathlib import Path
import re
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

    # 1) Add imports (after policy imports)
    policy_anchor = "from policy.policy import decide_routing, decide_retrieval\n"
    if policy_anchor not in src:
        die("missing policy import anchor")
    if "from tools.contract import ToolRequest\n" not in src:
        src = src.replace(policy_anchor, policy_anchor + "from tools.contract import ToolRequest\nfrom tools.wiring import get_tool_executor\n")
    if "from tools.wiring import get_tool_executor\n" not in src:
        die("failed to insert get_tool_executor import")

    # 2) Create executor once per graph build (inside build_simple_graph, before class _Graph)
    build_anchor = "def build_simple_graph(*, llm, vector_store, conv_store, persona_store, router_store):\n"
    if build_anchor not in src:
        die("missing build_simple_graph anchor")

    if "    executor = get_tool_executor()\n" not in src:
        src = src.replace(build_anchor, build_anchor + "    executor = get_tool_executor()\n")

    # 3) Replace the weather tooling block to use ToolExecutor
    tooling_pat = re.compile(
        r"(# Tooling\s*\n\s*tool_block = \"\"\s*\n\s*if is_weather:\s*\n)(.*?)(\n\s*# Build context)",
        flags=re.DOTALL,
    )
    m = tooling_pat.search(src)
    if not m:
        die("could not locate Tooling block with if is_weather")

    new_middle = """                state["tool"] = "weather"
                state["tool_args"] = parse_weather_args(text)

                # If no location was parsed, use the configured default.
                if not state["tool_args"].get("location") and not state["tool_args"].get("location_name"):
                    state["tool_args"]["location"] = DEFAULT_LOCATION_QUERY

                trace_id = (state.get("trace_id") or "trace_missing").strip() or "trace_missing"

                try:
                    started_at = datetime.now(timezone.utc)
                    req = ToolRequest(
                        trace_id=trace_id,
                        tool_name="weather",
                        args=state["tool_args"],
                        purpose="Realtime weather lookup (weather.gov)",
                        risk_level="READ_ONLY",
                    )
                    res = executor.execute(req)
                    ended_at = datetime.now(timezone.utc)

                    # Store full ToolResult envelope in state (standardized)
                    state["tool_result"] = res.to_dict()
                    state["tool_error"] = None if res.ok else res.error

                    # Never persist ephemeral tool calls
                    if state["tool"] not in EPHEMERAL_TOOLS:
                        log_tool_call(
                            trace_id=state.get("trace_id"),
                            user_id=user_id,
                            tool=state["tool"],
                            args=state["tool_args"],
                            result=state["tool_result"],
                            started_at=started_at,
                            ended_at=ended_at,
                        )

                except Exception as e:
                    state["tool_error"] = str(e)
                    state["tool_result"] = {"ok": False, "error": str(e)}

                # Build a context tool block for LLM use (if needed)
                if (state.get("tool_result") or {}).get("ok"):
                    _r = (state.get("tool_result") or {}).get("result") or {}
                    tool_block = f"TOOL RESULT (Weather): {_r.get('summary','')}"
"""
    src = src[:m.start(2)] + new_middle + src[m.end(2):]

    # 4) Fix deterministic weather answer extraction for ToolResult envelope
    det_pat = re.compile(
        r"(# Phase 6 tool-first invariant: if a tool succeeded, return a deterministic tool answer \(no LLM\)\s*\n\s*if state\.get\(\"tool\"\) == \"weather\" and \(state\.get\(\"tool_result\"\) or \{\}\)\.get\(\"ok\"\):\s*\n)"
        r"(\s*loc = .*?\n\s*summ = .*?\n\s*state\[\"answer\"\] = .*?\n\s*return state\s*\n)",
        flags=re.DOTALL,
    )
    dm = det_pat.search(src)
    if not dm:
        die("could not locate deterministic weather answer block")

    new_det = """                tr = state.get("tool_result") or {}
                rr = tr.get("result") or {}
                loc = rr.get("location") or (state.get("tool_args") or {}).get("location") or ""
                summ = (rr.get("summary") or "").strip()
                state["answer"] = f"{loc}: {summ}" if loc else summ
                return state
"""
    src = src[:dm.start(2)] + new_det + src[dm.end(2):]

    # Write .new and compile-check before swapping
    tmp = ORCH.with_suffix(".py.new")
    tmp.write_text(src)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"orchestrator.py.pre_tool_executor_weather.{ts}.bak"
    backup.write_text(ORCH.read_text(errors="replace"))

    ORCH.write_text(src)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: orchestrator.py now executes weather via ToolExecutor (backup: {backup})")

if __name__ == "__main__":
    main()
