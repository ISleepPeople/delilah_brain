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

    # Required anchors from the current file
    must = [
        'state["policy"] = {',
        '# Phase 6.0 invariant: tool-intent bypasses RAG (force tool early)',
        'if state.get("policy", {}).get("intent") == "tool" and state.get("policy", {}).get("tool_name") == "weather":',
        '# Tooling',
        'if is_weather:',
        '# Phase 6 tool-first invariant: if a tool succeeded, return a deterministic tool answer (no LLM)',
        '# Tool intent hard-stop: if the weather tool failed, DO NOT fall back to LLM (prevents hallucinations).',
    ]
    for a in must:
        if a not in src:
            die(f"missing anchor: {a}")

    # 1) Generalize the "force tool early" block (weather-only -> any policy tool_name)
    old_force = (
        '            # Phase 6.0 invariant: tool-intent bypasses RAG (force tool early)\n'
        '            if state.get("policy", {}).get("intent") == "tool" and state.get("policy", {}).get("tool_name") == "weather":\n'
        '                state["tool"] = "weather"\n'
    )
    new_force = (
        '            # Phase 6.0 invariant: tool-intent bypasses RAG (force tool early)\n'
        '            if state.get("policy", {}).get("intent") == "tool" and state.get("policy", {}).get("tool_name"):\n'
        '                state["tool"] = state.get("policy", {}).get("tool_name")\n'
    )
    if old_force not in src:
        die("force-tool block does not match expected text (abort)")
    src = src.replace(old_force, new_force, 1)

    # 2) Replace "ephemeral tool intent" definition to include generic tool intents
    old_det = (
        '            # Determine if this is an ephemeral tool intent (weather, etc.)\n'
        '            is_weather = (state.get("tool") == "weather") or detect_weather_intent(text)\n'
    )
    new_det = (
        '            # Determine if this is a policy tool intent (Tool APIs v1) or a heuristic weather intent (legacy)\n'
        '            policy_tool = state.get("policy", {}).get("tool_name")\n'
        '            is_tool_intent = (state.get("policy", {}).get("intent") == "tool") and bool(policy_tool)\n'
        '            # Weather can still be triggered heuristically, but policy tool-intent always bypasses RAG.\n'
        '            is_weather = ((state.get("tool") or policy_tool) == "weather") or detect_weather_intent(text)\n'
    )
    if old_det not in src:
        die("tool-intent detection block does not match expected text (abort)")
    src = src.replace(old_det, new_det, 1)

    # 3) Ensure tool intents bypass convo+RAG (not just weather)
    old_bypass = '            if not is_weather:\n'
    new_bypass = '            if (not is_tool_intent) and (not is_weather):\n'
    if old_bypass not in src:
        die("missing bypass anchor 'if not is_weather:' (abort)")
    src = src.replace(old_bypass, new_bypass, 1)

    # 4) Replace Tooling block (weather-only -> generic tool execution via ToolRequest)
    start_anchor = '            # Tooling\n            tool_block = ""\n            if is_weather:\n'
    end_anchor = '\n\n            # Build context\n'
    s = src.find(start_anchor)
    if s == -1:
        die("could not find tooling start anchor")
    e = src.find(end_anchor, s)
    if e == -1:
        die("could not find tooling end anchor")

    new_tooling = (
        '            # Tooling\n'
        '            tool_block = ""\n'
        '            if is_tool_intent or is_weather:\n'
        '                # Choose tool deterministically\n'
        '                tool_name = state.get("tool") or (policy_tool if is_tool_intent else "weather")\n'
        '                state["tool"] = tool_name\n'
        '                trace_id = (state.get("trace_id") or "trace_missing").strip() or "trace_missing"\n'
        '\n'
        '                try:\n'
        '                    started_at = datetime.now(timezone.utc)\n'
        '\n'
        '                    # Build tool args + ToolRequest\n'
        '                    req = None\n'
        '                    if tool_name == "weather":\n'
        '                        state["tool_args"] = parse_weather_args(text)\n'
        '                        if not state["tool_args"].get("location") and not state["tool_args"].get("location_name"):\n'
        '                            state["tool_args"]["location"] = DEFAULT_LOCATION_QUERY\n'
        '                        req = ToolRequest(\n'
        '                            trace_id=trace_id,\n'
        '                            tool_name="weather",\n'
        '                            args=state["tool_args"],\n'
        '                            purpose="Realtime weather lookup (weather.gov)",\n'
        '                            risk_level="READ_ONLY",\n'
        '                        )\n'
        '                    elif tool_name == "system.health_check":\n'
        '                        state["tool_args"] = {}\n'
        '                        req = ToolRequest(\n'
        '                            trace_id=trace_id,\n'
        '                            tool_name="system.health_check",\n'
        '                            args=state["tool_args"],\n'
        '                            purpose="Local system health check",\n'
        '                            risk_level="READ_ONLY",\n'
        '                        )\n'
        '                    elif tool_name == "system.get_versions":\n'
        '                        state["tool_args"] = {}\n'
        '                        req = ToolRequest(\n'
        '                            trace_id=trace_id,\n'
        '                            tool_name="system.get_versions",\n'
        '                            args=state["tool_args"],\n'
        '                            purpose="Return running component versions",\n'
        '                            risk_level="READ_ONLY",\n'
        '                        )\n'
        '                    elif tool_name == "mqtt.publish":\n'
        '                        import re as _re\n'
        '                        t = text or ""\n'
        '                        mt = _re.search(r"(?:topic\\s*:?\\s*)([A-Za-z0-9_\\-\\/\\.]+)", t, flags=_re.IGNORECASE)\n'
        '                        mp = _re.search(r"(?:payload\\s*:?\\s*)(.+)$", t, flags=_re.IGNORECASE)\n'
        '                        state["tool_args"] = {}\n'
        '                        if mt:\n'
        '                            state["tool_args"]["topic"] = mt.group(1)\n'
        '                        if mp:\n'
        '                            state["tool_args"]["payload"] = mp.group(1).strip()\n'
        '                        if not state["tool_args"].get("topic") or not state["tool_args"].get("payload"):\n'
        '                            state["tool_result"] = {"ok": False, "error": "mqtt.publish requires topic and payload", "result": {"tool": "mqtt.publish"}}\n'
        '                            state["tool_error"] = state["tool_result"]["error"]\n'
        '                            req = None\n'
        '                        else:\n'
        '                            req = ToolRequest(\n'
        '                                trace_id=trace_id,\n'
        '                                tool_name="mqtt.publish",\n'
        '                                args=state["tool_args"],\n'
        '                                purpose="Publish MQTT message (explicit user request)",\n'
        '                                risk_level="WRITE",\n'
        '                            )\n'
        '                    else:\n'
        '                        state["tool_args"] = {}\n'
        '                        state["tool_result"] = {"ok": False, "error": f"unknown tool: {tool_name}", "result": {"tool": tool_name}}\n'
        '                        state["tool_error"] = state["tool_result"]["error"]\n'
        '                        req = None\n'
        '\n'
        '                    if req is not None:\n'
        '                        res = executor.execute(req)\n'
        '                        ended_at = datetime.now(timezone.utc)\n'
        '                        state["tool_result"] = res.to_dict()\n'
        '                        state["tool_error"] = None if res.ok else res.error\n'
        '\n'
        '                        # Never persist ephemeral tools\n'
        '                        if state["tool"] not in EPHEMERAL_TOOLS:\n'
        '                            log_tool_call(\n'
        '                                trace_id=state.get("trace_id"),\n'
        '                                user_id=user_id,\n'
        '                                tool=state["tool"],\n'
        '                                args=state["tool_args"],\n'
        '                                result=state["tool_result"],\n'
        '                                started_at=started_at,\n'
        '                                ended_at=ended_at,\n'
        '                            )\n'
        '\n'
        '                except Exception as e:\n'
        '                    state["tool_error"] = str(e)\n'
        '                    state["tool_result"] = {"ok": False, "error": str(e), "result": {"tool": state.get("tool")}}\n'
        '\n'
        '                # Build a context tool block for LLM use (if needed)\n'
        '                if (state.get("tool_result") or {}).get("ok"):\n'
        '                    _r = (state.get("tool_result") or {}).get("result") or {}\n'
        '                    tool_block = f"TOOL RESULT ({state.get(\'tool\')}): {_r.get(\'summary\',\'\')}"\n'
    )

    src = src[:s] + new_tooling + src[e:]

    # 5) Generalize tool-first hard-stop blocks (weather-only -> any tool)
    old_success = (
        '            # Phase 6 tool-first invariant: if a tool succeeded, return a deterministic tool answer (no LLM)\n'
        '            if state.get("tool") == "weather" and (state.get("tool_result") or {}).get("ok"):\n'
    )
    if old_success not in src:
        die("missing weather-only success block anchor (abort)")

    # Replace the entire weather-only success+failure blocks with generic versions.
    # We anchor from the success comment through the end of the failure block return.
    succ_pos = src.find('            # Phase 6 tool-first invariant: if a tool succeeded, return a deterministic tool answer (no LLM)\n')
    fail_marker = '            # Tool intent hard-stop: if the weather tool failed, DO NOT fall back to LLM (prevents hallucinations).\n'
    fail_pos = src.find(fail_marker, succ_pos)
    if fail_pos == -1:
        die("missing weather-only failure marker (abort)")
    # Find end of failure block (the first 'return state' after failure marker)
    end_ret = src.find("return state", fail_pos)
    if end_ret == -1:
        die("could not locate return state for failure block")
    end_line = src.find("\n", end_ret)
    if end_line == -1:
        end_line = len(src)

    generic_blocks = (
        '            # Phase 6 tool-first invariant: if a tool succeeded, return a deterministic tool answer (no LLM)\n'
        '            if state.get("tool") and (state.get("tool_result") or {}).get("ok"):\n'
        '                tool = state.get("tool")\n'
        '                tr = state.get("tool_result") or {}\n'
        '                rr = tr.get("result") or {}\n'
        '                summ = (rr.get("summary") or "").strip()\n'
        '                if tool == "weather":\n'
        '                    loc = rr.get("location") or (state.get("tool_args") or {}).get("location") or ""\n'
        '                    state["answer"] = f"{loc}: {summ}" if loc else summ\n'
        '                else:\n'
        '                    state["answer"] = summ or str(rr)\n'
        '                state["source"] = "tool"\n'
        '                state["used_context"] = False\n'
        '                state["num_docs"] = 0\n'
        '                state["used_conversation_context"] = False\n'
        '                return state\n'
        '\n'
        '            # Tool intent hard-stop: if a tool failed, DO NOT fall back to LLM (prevents hallucinations).\n'
        '            if state.get("tool") and (state.get("tool_result") or {}).get("ok") is False:\n'
        '                tool = state.get("tool")\n'
        '                tr = state.get("tool_result") or {}\n'
        '                rr = tr.get("result") or {}\n'
        '                err = tr.get("error") or rr.get("error") or state.get("tool_error") or "tool failed"\n'
        '                if tool == "weather":\n'
        '                    loc = rr.get("location") or (state.get("tool_args") or {}).get("location") or (state.get("tool_args") or {}).get("location_name") or ""\n'
        '                    state["answer"] = f"Weather lookup failed for {loc}: {err}" if loc else f"Weather lookup failed: {err}"\n'
        '                else:\n'
        '                    state["answer"] = f"{tool} failed: {err}"\n'
        '                state["source"] = "tool_error"\n'
        '                state["used_context"] = False\n'
        '                state["num_docs"] = 0\n'
        '                state["used_conversation_context"] = False\n'
        '                return state\n'
    )

    src = src[:succ_pos] + generic_blocks + src[end_line+1:]

    # Compile-check before writing
    tmp = ORCH.with_suffix(".py.new")
    tmp.write_text(src)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"orchestrator.py.pre_tool_apis_v1_generic.{ts}.bak"
    backup.write_text(ORCH.read_text(errors="replace"))

    ORCH.write_text(src)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: orchestrator generic tool intents (Tool APIs v1) enabled (backup: {backup})")

if __name__ == "__main__":
    main()
