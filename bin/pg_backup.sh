#!/usr/bin/env bash
set -euo pipefail

# ---- Config ----
BACKUP_DIR="/home/dad/delilah_workspace/backups/postgres"
RETENTION_COUNT=14   # keep last 14 backups
CONTAINER="delilah_postgres"
DB_NAME="delilah"
DB_USER="delilah"

TS="$(date -u +%Y%m%d_%H%M%SZ)"
OUT="$BACKUP_DIR/delilah_pg_${TS}.sql.gz"

mkdir -p "$BACKUP_DIR"

docker exec "$CONTAINER" \
  pg_dump -U "$DB_USER" "$DB_NAME" \
  | gzip > "$OUT"

if [[ ! -s "$OUT" ]]; then
  echo "[pg_backup] ERROR: backup file is empty"
  exit 1
fi

ls -1t "$BACKUP_DIR"/delilah_pg_*.sql.gz | tail -n +$((RETENTION_COUNT+1)) | xargs -r rm --

echo "[pg_backup] OK: $(basename "$OUT")"
