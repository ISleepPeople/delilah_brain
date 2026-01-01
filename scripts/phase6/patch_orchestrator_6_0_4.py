from __future__ import annotations

from pathlib import Path
import re
import py_compile
import sys

p = Path("/home/dad/delilah_workspace/orchestrator.py")
src = p.read_text(errors="replace")

# 1) Insert policy imports (after import re)
imp_line = "from policy.policy import decide_routing, decide_retrieval\n"
if imp_line not in src:
    m = re.search(r"^import re\s*$", src, flags=re.MULTILINE)
    if not m:
        print("PATCH ERROR: missing import re anchor", file=sys.stderr)
        sys.exit(1)
    src = src[:m.end()] + "\n\n" + imp_line + src[m.end():]

# 2) Insert policy decision block inside invoke()
policy_block = '''
            # Phase 6.0 policy (deterministic routing + retrieval invariants)
            policy_routing = decide_routing(text)
            policy_retrieval = decide_retrieval(routing=policy_routing, default_collections=[])

            state["policy"] = {
                "intent": policy_routing.intent.value,
                "volatility": policy_routing.volatility.value,
                "expert_id": policy_routing.expert_id,
                "tool_name": policy_routing.tool_name,
                "use_rag": policy_retrieval.use_rag,
                "top_k": policy_retrieval.top_k,
            }
'''
if 'state["policy"] = {' not in src:
    anchor = re.search(
        r'(user_id\s*=\s*\(state\.get\("user_id"\)\s*or\s*state\.get\("user"\)\)\s*or\s*"ryan"\s*)',
        src
    )
    if not anchor:
        print("PATCH ERROR: missing user_id anchor in invoke()", file=sys.stderr)
        sys.exit(1)
    i = anchor.end(1)
    src = src[:i] + policy_block + src[i:]

# 3) Enforce invariant: tool-intent forces tool early (after state.update({... "tool": None ...}))
force_tool = '''
            # Phase 6.0 invariant: tool-intent bypasses RAG (force tool early)
            if state.get("policy", {}).get("intent") == "tool" and state.get("policy", {}).get("tool_name") == "weather":
                state["tool"] = "weather"
'''
if "force tool early" not in src:
    m = re.search(r'state\.update\(\s*\{.*?\}\s*\)\s*', src, flags=re.DOTALL)
    if not m or '"tool": None' not in m.group(0):
        print('PATCH ERROR: missing state.update({... "tool": None ...}) anchor', file=sys.stderr)
        sys.exit(1)
    src = src[:m.end()] + force_tool + src[m.end():]

# 4) Replace similarity_search(text, k=3) with policy top_k
src = re.sub(
    r"similarity_search\(\s*text\s*,\s*k\s*=\s*3\s*\)",
    "similarity_search(text, k=int(state.get('policy', {}).get('top_k', 3)))",
    src,
)

# Write .new, validate compile, then atomic swap
tmp = Path("/home/dad/delilah_workspace/orchestrator.py.new")
tmp.write_text(src)
py_compile.compile(str(tmp), doraise=True)

bak = Path("/home/dad/delilah_workspace/orchestrator.py.prev")
if bak.exists():
    bak.unlink()

p.rename(bak)
tmp.rename(p)
bak.unlink(missing_ok=True)

print("PATCH OK: orchestrator.py updated (atomic swap).")
