#!/usr/bin/env bash
set -euo pipefail

TS="$(date -u +%Y%m%d_%H%M%SZ)"

DATASETS=(
  "delilah-pool/backups"
  "delilah-pool/databases"
  "delilah-pool/ai/qdrant"
)

for ds in "${DATASETS[@]}"; do
  zfs snapshot "${ds}@auto-${TS}"
done

echo "[zfs-snapshot] OK @ ${TS}"
