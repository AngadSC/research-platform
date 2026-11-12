#!/usr/bin/env sh
# Rebuild and restart the stack from the code already in ~/app. Runs on the server.
set -eu
cd "$HOME/app/deploy"
C="docker compose -f docker-compose.prod.yml"
$C build
$C run --rm backend python manage.py migrate
$C up -d
# The deploy unpacks a new Caddyfile over the old one; a single-file bind mount keeps the old
# file until the container is recreated, so recreate Caddy every time (about a second offline).
$C up -d --force-recreate --no-deps caddy
docker image prune -f >/dev/null
$C ps --format "table {{.Service}}\t{{.Status}}"
