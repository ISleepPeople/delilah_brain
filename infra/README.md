# Delilah Infrastructure (Git-tracked)

This repo tracks infrastructure *intent* and topology, not runtime state.

## Live locations on server
- /srv/delilah/docker-compose.yml
  - Authoritative compose for Delilah runtime services.

## Git-tracked copies
- infra/srv/delilah/docker-compose.yml
  - Copied from /srv/delilah/docker-compose.yml via scripts/sync_infra.sh
- infra/srv/delilah/delilah.rendered.yml
  - Output of `docker compose config` for debugging and reproducibility

## What is NOT in Git
- secrets (.env)
- Docker volumes / runtime state
- database data directories
- Qdrant storage
