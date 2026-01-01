#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SRC_COMPOSE="/srv/delilah/docker-compose.yml"
DST_DIR="$REPO_ROOT/infra/srv/delilah"
DST_COMPOSE="$DST_DIR/docker-compose.yml"

# Rendered compose (resolved config)
cd /srv/delilah
docker compose config > /tmp/delilah.rendered.yml
cp -a /tmp/delilah.rendered.yml "$DST_DIR/delilah.rendered.yml"
chown "$(id -u):$(id -g)" "$DST_DIR/delilah.rendered.yml"


mkdir -p "$DST_DIR"

sudo cp -a "$SRC_COMPOSE" "$DST_COMPOSE"
sudo chown "$(id -u):$(id -g)" "$DST_COMPOSE"

echo "Synced: $SRC_COMPOSE -> $DST_COMPOSE"
git status --porcelain "$DST_COMPOSE" || true
