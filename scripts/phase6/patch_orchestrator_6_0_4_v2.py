from __future__ import annotations

from pathlib import Path
import re
import sys
import time
import py_compile


ORCH = Path("/home/dad/delilah_workspace/orchestrator.py")
BACKUP_DIR = Path("/home/dad/delilah_workspace/backups/phase6")


def die(msg: str) -> None:
    print(f"PATCH ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def already_patched(src: str) -> bool:
    return "Phase 6.0 policy (deterministic routing + retrieval invariants)" in src


def insert_after_import_re(src: str) -> str:
    imp_line = "from policy.policy import decide_routing, decide_retrieval\n"
    if imp_line in src:
        return src

    m = re.search(r"^import re\s*$", src, flags=re.MULTILINE)
    if not m:
        die("missing anchor: 'import re'")

    return src[: m.end()] + "\n\n" + imp_line + src[m.end() :]


def insert_policy_block_after_user_id(src: str) -> str:
    if 'state["policy"] = {' in src:
        return src

    # Match your actual line:
    # user_id = (state.get("user_id") or "ryan").strip() or "ryan"
    pat = re.compile(
        r'^(?P<indent>\s*)user_id\s*=\s*\(state\.get\("user_id"\)\s*or\s*"ryan"\)\.strip\(\)\s*or\s*"ryan"\s*$',
        flags=re.MULTILINE,
    )
    m = pat.search(src)
    if not m:
        die('missing anchor: user_id assignment line (expected: user_id = (state.get("user_id") or "ryan").strip() or "ryan")')

    indent = m.group("indent")
    block = (
        "\n"
        f"{indent}# Phase 6.0 policy (deterministic routing + retrieval invariants)\n"
        f"{indent}policy_routing = decide_routing(text)\n"
        f"{indent}policy_retrieval = decide_retrieval(routing=policy_routing, default_collections=[])\n"
        "\n"
        f'{indent}state["policy"] = {{\n'
        f'{indent}    "intent": policy_routing.intent.value,\n'
        f'{indent}    "volatility": policy_routing.volatility.value,\n'
        f'{indent}    "expert_id": policy_routing.expert_id,\n'
        f'{indent}    "tool_name": policy_routing.tool_name,\n'
        f'{indent}    "use_rag": policy_retrieval.use_rag,\n'
        f'{indent}    "top_k": policy_retrieval.top_k,\n'
        f"{indent}}}\n"
    )

    insert_at = m.end()
    return src[:insert_at] + block + src[insert_at:]


def insert_force_tool_after_state_update(src: str) -> str:
    if "force tool early" in src:
        return src

    # Find the first state.update({...}) block that includes "tool": None
    upd_pat = re.compile(r"state\.update\(\s*\{.*?\}\s*\)\s*", flags=re.DOTALL)
    for m in upd_pat.finditer(src):
        chunk = m.group(0)
        if '"tool": None' in chunk or "'tool': None" in chunk:
            insert_at = m.end()
            indent_m = re.search(r"^(\s*)state\.update", chunk, flags=re.MULTILINE)
            indent = indent_m.group(1) if indent_m else "            "
            snippet = (
                f"\n{indent}# Phase 6.0 invariant: tool-intent bypasses RAG (force tool early)\n"
                f'{indent}if state.get("policy", {{}}).get("intent") == "tool" and state.get("policy", {{}}).get("tool_name") == "weather":\n'
                f'{indent}    state["tool"] = "weather"\n'
            )
            return src[:insert_at] + snippet + src[insert_at:]

    die('missing anchor: state.update({... "tool": None ...})')


def replace_is_weather_line(src: str) -> str:
    # Replace: is_weather = detect_weather_intent(text)
    pat = re.compile(r"^(?P<indent>\s*)is_weather\s*=\s*detect_weather_intent\(text\)\s*$", flags=re.MULTILINE)
    m = pat.search(src)
    if not m:
        # Not fatal: file may not use this exact variable; continue.
        return src

    indent = m.group("indent")
    repl = (
        f'{indent}is_weather = ((state.get("policy", {{}}).get("intent") == "tool") and '
        f'(state.get("policy", {{}}).get("tool_name") == "weather")) or detect_weather_intent(text)'
    )
    return pat.sub(repl, src, count=1)


def replace_similarity_k(src: str) -> str:
    # Replace similarity_search(text, k=3) -> policy-controlled k
    return re.sub(
        r"similarity_search\(\s*text\s*,\s*k\s*=\s*3\s*\)",
        'similarity_search(text, k=int(state.get("policy", {}).get("top_k", 3)))',
        src,
    )


def main() -> None:
    if not ORCH.exists():
        die(f"orchestrator.py not found at {ORCH}")

    original = ORCH.read_text(errors="replace")

    if already_patched(original):
        print("PATCH OK: orchestrator.py already contains Phase 6.0 policy block; no changes applied.")
        return

    src = original
    src = insert_after_import_re(src)
    src = insert_policy_block_after_user_id(src)
    src = insert_force_tool_after_state_update(src)
    src = replace_is_weather_line(src)
    src = replace_similarity_k(src)

    if src == original:
        die("no changes produced (unexpected)")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"orchestrator.py.pre_phase6_0_4_v2.{ts}.bak"
    backup.write_text(original)

    tmp = Path("/home/dad/delilah_workspace/orchestrator.py.new")
    tmp.write_text(src)

    # Validate compilation before swap
    py_compile.compile(str(tmp), doraise=True)

    # Atomic-ish swap
    ORCH.write_text(src)

    print(f"PATCH OK: orchestrator.py updated (backup: {backup})")


if __name__ == "__main__":
    main()
