#!/usr/bin/env sh
# Rebuild and restart the stack from the code already in ~/app. Runs on the server.
set -eu
cd "$HOME/app/deploy"
C="docker compose -f docker-compose.prod.yml"
$C build
$C run --rm backend python manage.py migrate
$C up -d
docker image prune -f >/dev/null
$C ps --format "table {{.Service}}\t{{.Status}}"
