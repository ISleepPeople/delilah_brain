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

    # 1) Remove the unreachable, mis-indented failure block (currently inside success block after return).
    marker = "Tool intent hard-stop: if the weather tool failed, DO NOT fall back to LLM"
    if marker in src:
        start = src.find(marker)
        # back up to the indentation of that comment line
        line_start = src.rfind("\n", 0, start) + 1
        # remove until the end of that failure block (the next 'return state' after marker)
        ret = src.find("return state", start)
        if ret == -1:
            die("found failure marker but could not find 'return state' inside that block")
        ret_line_end = src.find("\n", ret)
        if ret_line_end == -1:
            ret_line_end = len(src)
        src = src[:line_start] + src[ret_line_end+1:]

    # 2) Find the weather-success tool-first block and replace it with a version that:
    #    - sets source="tool"
    #    - forces no-RAG accounting
    #    - returns deterministically
    success_anchor = 'if state.get("tool") == "weather" and (state.get("tool_result") or {}).get("ok"):'
    pos = src.find(success_anchor)
    if pos == -1:
        die("missing weather success tool-first block anchor")

    # Replace the body up through its 'return state' line.
    block_start = src.rfind("\n", 0, pos) + 1
    ret = src.find("return state", pos)
    if ret == -1:
        die("could not locate 'return state' in weather success block")
    ret_line_end = src.find("\n", ret)
    if ret_line_end == -1:
        ret_line_end = len(src)

    # Indentation at the if-line
    if_line = src[block_start: src.find("\n", block_start)]
    indent = if_line.split("if", 1)[0]

    new_success = f'''{indent}if state.get("tool") == "weather" and (state.get("tool_result") or {{}}).get("ok"):
{indent}    tr = state.get("tool_result") or {{}}
{indent}    rr = tr.get("result") or {{}}
{indent}    loc = rr.get("location") or (state.get("tool_args") or {{}}).get("location") or ""
{indent}    summ = (rr.get("summary") or "").strip()
{indent}    state["answer"] = f"{{loc}}: {{summ}}" if loc else summ
{indent}    state["source"] = "tool"
{indent}    state["used_context"] = False
{indent}    state["num_docs"] = 0
{indent}    state["used_conversation_context"] = False
{indent}    return state
'''

    src = src[:block_start] + new_success + src[ret_line_end+1:]

    # 3) Insert a proper weather-failure hard-stop block immediately AFTER the success block,
    #    at the same indentation level (so it runs when tool_result.ok is False).
    if "state[\"source\"] = \"tool_error\"" not in src:
        insert_point = src.find(new_success) + len(new_success)
        new_failure = f'''
{indent}# Tool intent hard-stop: if the weather tool failed, DO NOT fall back to LLM (prevents hallucinations).
{indent}if state.get("tool") == "weather" and (state.get("tool_result") or {{}}).get("ok") is False:
{indent}    tr = state.get("tool_result") or {{}}
{indent}    rr = tr.get("result") or {{}}
{indent}    loc = rr.get("location") or (state.get("tool_args") or {{}}).get("location") or (state.get("tool_args") or {{}}).get("location_name") or ""
{indent}    err = tr.get("error") or rr.get("error") or state.get("tool_error") or "weather tool failed"
{indent}    state["answer"] = f"Weather lookup failed for {{loc}}: {{err}}" if loc else f"Weather lookup failed: {{err}}"
{indent}    state["source"] = "tool_error"
{indent}    state["used_context"] = False
{indent}    state["num_docs"] = 0
{indent}    state["used_conversation_context"] = False
{indent}    return state
'''
        src = src[:insert_point] + new_failure + src[insert_point:]

    # Compile-check before writing
    tmp = ORCH.with_suffix(".py.new")
    tmp.write_text(src)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"orchestrator.py.pre_fix_weather_tool_first.{ts}.bak"
    backup.write_text(ORCH.read_text(errors="replace"))

    ORCH.write_text(src)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: fixed weather tool-first success+failure blocks (backup: {backup})")

if __name__ == "__main__":
    main()
