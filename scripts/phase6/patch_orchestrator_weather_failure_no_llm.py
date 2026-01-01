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

    anchor = '# Phase 6 tool-first invariant: if a tool succeeded, return a deterministic tool answer (no LLM)\n'
    if anchor not in src:
        die("missing deterministic tool-first anchor comment")

    # Find the existing weather-success early return block and insert a failure early return immediately after it.
    success_marker = 'if state.get("tool") == "weather" and (state.get("tool_result") or {}).get("ok"):\n'
    if success_marker not in src:
        die("missing weather tool-first success block")

    insert_after = (
        'if state.get("tool") == "weather" and (state.get("tool_result") or {}).get("ok"):\n'
    )

    # We insert a second block *after* the existing success block's `return state`.
    # Anchor on the exact `return state` that belongs to the success block by searching nearby.
    idx = src.find(insert_after)
    if idx == -1:
        die("could not locate insert point")

    # Locate the first "return state" after the success block begins.
    ret_idx = src.find("return state", idx)
    if ret_idx == -1:
        die("could not locate return state in success block")

    # Move to end of that line.
    line_end = src.find("\n", ret_idx)
    if line_end == -1:
        die("could not locate end-of-line after return state")

    failure_block = """

                # Tool intent hard-stop: if the weather tool failed, DO NOT fall back to LLM (prevents hallucinations).
                if state.get("tool") == "weather" and (state.get("tool_result") or {}).get("ok") is False:
                    tr = state.get("tool_result") or {}
                    rr = tr.get("result") or {}
                    loc = rr.get("location") or (state.get("tool_args") or {}).get("location") or (state.get("tool_args") or {}).get("location_name") or ""
                    err = tr.get("error") or rr.get("error") or state.get("tool_error") or "weather tool failed"
                    state["answer"] = f"Weather lookup failed for {loc}: {err}" if loc else f"Weather lookup failed: {err}"
                    state["source"] = "tool_error"
                    state["used_context"] = False
                    state["num_docs"] = 0
                    return state
"""

    if "Tool intent hard-stop: if the weather tool failed" in src:
        print("PATCH OK: failure hard-stop already present; no changes.")
        raise SystemExit(0)

    new_src = src[:line_end+1] + failure_block + src[line_end+1:]

    # Compile-check before swap
    tmp = ORCH.with_suffix(".py.new")
    tmp.write_text(new_src)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"orchestrator.py.pre_weather_failure_no_llm.{ts}.bak"
    backup.write_text(src)

    ORCH.write_text(new_src)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: orchestrator.py now hard-stops on weather tool failure (backup: {backup})")

if __name__ == "__main__":
    main()
