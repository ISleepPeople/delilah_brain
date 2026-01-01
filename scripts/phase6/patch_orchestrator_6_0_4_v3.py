from __future__ import annotations

from pathlib import Path
import re
import sys
import time
import py_compile

REPO = Path("/home/dad/delilah_workspace")
ORCH = REPO / "orchestrator.py"
BACKUP_DIR = REPO / "backups" / "phase6"

POLICY_IMPORT = "from policy.policy import decide_routing, decide_retrieval\n"

POLICY_BLOCK_SENTINEL = "Phase 6.0 policy (deterministic routing + retrieval invariants)"
FORCE_TOOL_SENTINEL = "Phase 6.0 invariant: tool-intent bypasses RAG (force tool early)"


def die(msg: str) -> None:
    print(f"PATCH ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def read_text(p: Path) -> str:
    return p.read_text(errors="replace")


def write_text(p: Path, s: str) -> None:
    p.write_text(s)


def find_invoke_slice(src: str) -> tuple[int, int, str]:
    """
    Return (start_idx, end_idx, indent) for the invoke() method block text.

    We locate:
      'def invoke(' line, capture its indent
      then include everything until the next line that has indent <= def indent and is not blank/comment.

    This avoids fragile anchors elsewhere in the file.
    """
    m = re.search(r"^(?P<indent>\s*)def invoke\(\s*self\s*,", src, flags=re.MULTILINE)
    if not m:
        die("could not find 'def invoke(self,' in orchestrator.py")

    indent = m.group("indent")
    start = m.start()

    # Find end: next line with indent <= current indent and starts with 'def ' or 'class ' at that level
    # We scan line-by-line after start.
    lines = src[m.start():].splitlines(True)
    # First line is def invoke itself; invoke body begins after that.
    cur_len = len(indent)

    end_rel = 0
    for i, line in enumerate(lines[1:], start=1):
        end_rel += len(lines[i-1])
        if not line.strip():
            continue
        # ignore comments
        if line.lstrip().startswith("#"):
            continue
        # compute indentation
        line_indent = len(line) - len(line.lstrip(" "))
        if line_indent <= cur_len and (line.lstrip().startswith("def ") or line.lstrip().startswith("class ")):
            # end is start + end_rel
            return start, start + end_rel, indent

    # If invoke is last block, take to EOF
    return start, len(src), indent


def ensure_policy_import(src: str) -> str:
    if POLICY_IMPORT in src:
        return src
    m = re.search(r"^import re\s*$", src, flags=re.MULTILINE)
    if not m:
        die("missing anchor: 'import re' for import insertion")
    return src[:m.end()] + "\n\n" + POLICY_IMPORT + src[m.end():]


def insert_policy_block(invoke_src: str) -> str:
    if POLICY_BLOCK_SENTINEL in invoke_src:
        return invoke_src

    # Anchor on your known user_id line inside invoke()
    pat = re.compile(
        r'^(?P<indent>\s*)user_id\s*=\s*\(state\.get\("user_id"\)\s*or\s*"ryan"\)\.strip\(\)\s*or\s*"ryan"\s*$',
        flags=re.MULTILINE,
    )
    m = pat.search(invoke_src)
    if not m:
        die("invoke(): could not find user_id assignment anchor")

    indent = m.group("indent")
    block = (
        "\n"
        f"{indent}# {POLICY_BLOCK_SENTINEL}\n"
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
    return invoke_src[:m.end()] + block + invoke_src[m.end():]


def insert_force_tool(invoke_src: str) -> str:
    if FORCE_TOOL_SENTINEL in invoke_src:
        return invoke_src

    # Find state.update({...}) within invoke() that includes "tool": None
    upd_pat = re.compile(r"state\.update\(\s*\{.*?\}\s*\)\s*", flags=re.DOTALL)
    for m in upd_pat.finditer(invoke_src):
        chunk = m.group(0)
        if '"tool": None' in chunk or "'tool': None" in chunk:
            # Determine indentation from the actual state.update line in invoke_src
            line_start = invoke_src.rfind("\n", 0, m.start()) + 1
            indent = re.match(r"\s*", invoke_src[line_start:m.start()]).group(0)

            snippet = (
                "\n"
                f"{indent}# {FORCE_TOOL_SENTINEL}\n"
                f'{indent}if state.get("policy", {{}}).get("intent") == "tool" and state.get("policy", {{}}).get("tool_name") == "weather":\n'
                f'{indent}    state["tool"] = "weather"\n'
            )
            return invoke_src[:m.end()] + snippet + invoke_src[m.end():]

    die('invoke(): missing anchor state.update({... "tool": None ...})')


def replace_similarity_k(invoke_src: str) -> str:
    return re.sub(
        r"similarity_search\(\s*text\s*,\s*k\s*=\s*3\s*\)",
        'similarity_search(text, k=int(state.get("policy", {}).get("top_k", 3)))',
        invoke_src,
    )


def main() -> None:
    if not ORCH.exists():
        die(f"missing {ORCH}")

    src = read_text(ORCH)

    # Do not proceed if orchestrator already contains both sentinels; idempotent behavior
    if POLICY_BLOCK_SENTINEL in src and FORCE_TOOL_SENTINEL in src:
        print("PATCH OK: orchestrator.py already contains Phase 6.0 policy wiring; no changes applied.")
        return

    src2 = ensure_policy_import(src)

    inv_start, inv_end, _inv_indent = find_invoke_slice(src2)
    invoke = src2[inv_start:inv_end]
    rest = src2[:inv_start], src2[inv_end:]

    invoke2 = invoke
    invoke2 = insert_policy_block(invoke2)
    invoke2 = insert_force_tool(invoke2)
    invoke2 = replace_similarity_k(invoke2)

    if invoke2 == invoke and src2 == src:
        die("no changes produced (unexpected)")

    # Assemble updated source
    out = rest[0] + invoke2 + rest[1]

    # Write .new and compile-check before swapping
    tmp = REPO / "orchestrator.py.new"
    write_text(tmp, out)
    py_compile.compile(str(tmp), doraise=True)

    # Backup original
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"orchestrator.py.pre_phase6_0_4_v3.{ts}.bak"
    write_text(backup, src)

    # Replace live file
    write_text(ORCH, out)

    print(f"PATCH OK: orchestrator.py updated (backup: {backup})")


if __name__ == "__main__":
    main()
