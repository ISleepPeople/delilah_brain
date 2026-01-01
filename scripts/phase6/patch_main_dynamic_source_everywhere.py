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

    # We expect hardcoded "rag_llm_graph" in at least the return dict.
    if '"source": "rag_llm_graph"' not in src:
        die('missing anchor: \'"source": "rag_llm_graph"\' (file differs from expected)')

    # 1) Fix the API response field.
    src = src.replace(
        '"source": "rag_llm_graph",',
        '"source": result.get("source", "rag_llm_graph"),',
        1
    )

    # 2) Fix pg_log_turn meta source (if present) so audit matches runtime.
    if 'meta={"source": "rag_llm_graph"}' in src:
        src = src.replace(
            'meta={"source": "rag_llm_graph"},',
            'meta={"source": result.get("source", "rag_llm_graph")},',
            1
        )

    tmp = MAIN.with_suffix(".py.new")
    tmp.write_text(src)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"main.py.pre_dynamic_source_everywhere.{ts}.bak"
    backup.write_text(MAIN.read_text(errors="replace"))

    MAIN.write_text(src)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: main.py now returns/logs dynamic source (backup: {backup})")

if __name__ == "__main__":
    main()
