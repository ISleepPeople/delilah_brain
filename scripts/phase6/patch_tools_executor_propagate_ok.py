from __future__ import annotations

from pathlib import Path
import time
import py_compile
import sys
import re

FILE = Path("/home/dad/delilah_workspace/tools/executor.py")
BACKUP_DIR = Path("/home/dad/delilah_workspace/backups/phase6")

def die(msg: str) -> None:
    print(f"PATCH ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)

def main() -> None:
    if not FILE.exists():
        die(f"missing {FILE}")

    src = FILE.read_text(errors="replace")

    # Anchor on the exact "out = impl(...)" and "res = ok_result(...)" structure in the current file.
    if "out = impl(req.args or {})" not in src:
        die("missing anchor: out = impl(req.args or {})")
    if "res = ok_result(" not in src:
        die("missing anchor: res = ok_result(")

    # Replace the block that unconditionally uses ok_result(...) with logic that honors out['ok'].
    pattern = re.compile(
        r"""
            (?P<prefix>\s*)out\s*=\s*impl\(req\.args\s*or\s*\{\}\)\s*\n
            (?P<mid>.*?)
            (?P<prefix2>\s*)res\s*=\s*ok_result\(\s*\n
            (?P<ok_body>.*?)
            (?P<prefix3>\s*)\)\s*\n
            (?P<suffix>\s*)#\s*attach\s*audit\s*without\s*mutating\s*frozen\s*dataclass:\s*create\s*a\s*new\s*ToolResult
        """,
        re.DOTALL | re.VERBOSE,
    )

    m = pattern.search(src)
    if not m:
        die("could not locate expected ok_result block near tool execution")

    indent = m.group("prefix")
    # Keep everything between out=... and res=ok_result(...) as-is (spec/audit construction).
    mid = m.group("mid")

    replacement = (
        f"{indent}out = impl(req.args or {{}})\n"
        f"{mid}"
        f"{indent}# Propagate semantic ok/error from tool payload when present.\n"
        f"{indent}semantic_ok = True\n"
        f"{indent}semantic_err = None\n"
        f"{indent}if isinstance(out, dict) and \"ok\" in out:\n"
        f"{indent}    semantic_ok = bool(out.get(\"ok\"))\n"
        f"{indent}    if not semantic_ok:\n"
        f"{indent}        semantic_err = out.get(\"error\") or \"tool returned ok=false\"\n"
        f"\n"
        f"{indent}if semantic_ok:\n"
        f"{indent}    res = ok_result(\n"
        f"{indent}        trace_id=req.trace_id,\n"
        f"{indent}        tool_name=req.tool_name,\n"
        f"{indent}        result=out or {{}},\n"
        f"{indent}        started_at_ms=started,\n"
        f"{indent}    )\n"
        f"{indent}else:\n"
        f"{indent}    # Use error_result for timestamps/duration, but preserve tool payload in result.\n"
        f"{indent}    _tmp = error_result(\n"
        f"{indent}        trace_id=req.trace_id,\n"
        f"{indent}        tool_name=req.tool_name,\n"
        f"{indent}        error=str(semantic_err),\n"
        f"{indent}        started_at_ms=started,\n"
        f"{indent}    )\n"
        f"{indent}    res = ToolResult(\n"
        f"{indent}        trace_id=_tmp.trace_id,\n"
        f"{indent}        tool_name=_tmp.tool_name,\n"
        f"{indent}        ok=_tmp.ok,\n"
        f"{indent}        result=out if isinstance(out, dict) else {{\"value\": out}},\n"
        f"{indent}        error=_tmp.error,\n"
        f"{indent}        started_at_ms=_tmp.started_at_ms,\n"
        f"{indent}        finished_at_ms=_tmp.finished_at_ms,\n"
        f"{indent}        duration_ms=_tmp.duration_ms,\n"
        f"{indent}        audit=None,\n"
        f"{indent}    )\n"
        f"\n"
        f"{m.group('suffix')}# attach audit without mutating frozen dataclass: create a new ToolResult"
    )

    new_src = src[:m.start()] + replacement + src[m.end():]

    # Compile-check before swapping
    tmp = FILE.with_suffix(".py.new")
    tmp.write_text(new_src)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"executor.py.pre_propagate_ok.{ts}.bak"
    backup.write_text(src)

    FILE.write_text(new_src)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: ToolExecutor now honors tool payload ok/error (backup: {backup})")

if __name__ == "__main__":
    main()
