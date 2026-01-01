from __future__ import annotations

from pathlib import Path
import time
import py_compile
import sys

MAIN = Path("/home/dad/delilah_workspace/main.py")
BACKUP_DIR = Path("/home/dad/delilah_workspace/backups/phase6")

def die(msg: str) -> None:
    print(f"PATCH ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)

def main() -> None:
    if not MAIN.exists():
        die(f"missing {MAIN}")

    src = MAIN.read_text(errors="replace")

    # Anchor on the response dict where source is currently hard-coded.
    old = '"source": "rag_llm_graph",'
    if old not in src:
        die('missing anchor: "source": "rag_llm_graph",')

    # Replace with dynamic source from orchestrator result.
    new = '"source": result.get("source", "rag_llm_graph"),'
    src2 = src.replace(old, new, 1)

    # Also ensure we return used_context / num_docs from result if present (already should, but keep safe).
    # No further changes; keep patch minimal.

    tmp = MAIN.with_suffix(".py.new")
    tmp.write_text(src2)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"main.py.pre_dynamic_source.{ts}.bak"
    backup.write_text(src)

    MAIN.write_text(src2)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: main.py now returns dynamic source from orchestrator result (backup: {backup})")

if __name__ == "__main__":
    main()
