#!/usr/bin/env bash
set -euo pipefail

REPO="/home/dad/delilah_workspace"

asdad() {
  # Run a command in the repo as dad, non-interactive, with a clean HOME
  sudo -u dad -H bash -lc "set -euo pipefail; cd ${REPO}; $*"
}

case "${1:-}" in
  gate)
    asdad "source .venv/bin/activate; ./scripts/phase6_gate.sh"
    ;;
  pycompile)
    asdad "source .venv/bin/activate; python -m py_compile orchestrator.py"
    ;;
  clean)
    # remove transient artifacts that can confuse troubleshooting
    asdad "rm -f orchestrator.py.new orchestrator.py.prev 2>/dev/null || true"
    ;;
  *)
    cat <<USAGE
Usage:
  scripts/phase6/p6.sh gate        # run Phase 6 pytest gate
  scripts/phase6/p6.sh pycompile   # compile-check orchestrator.py
  scripts/phase6/p6.sh clean       # remove transient .new/.prev artifacts
USAGE
    ;;
esac
