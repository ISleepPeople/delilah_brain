#!/usr/bin/env sh
set -e
echo "== Delilah Brain v2 status =="
date -u
echo
docker ps --filter "name=delilah_brain_v2" --format "Container: {{.Names}}  Status: {{.Status}}"
echo
curl -sS http://localhost:8801/health
echo
