#!/usr/bin/env sh
# Redeploy the committed code (HEAD) to a server set up as in docs/DEPLOY.md.
# Usage: deploy/push.sh [user@host]   (default: the test server)
# Secrets stay on the server in ~/app/deploy/.env.prod and .env; this never touches them.
set -eu
HOST="${1:-angad@66.209.180.131}"
cd "$(git rev-parse --show-toplevel)"
git archive --format=tar HEAD | ssh "$HOST" 'tar -x -C ~/app'
ssh "$HOST" 'cd ~/app/deploy && C="docker compose -f docker-compose.prod.yml" \
  && $C build \
  && $C run --rm backend python manage.py migrate \
  && $C up -d \
  && docker image prune -f >/dev/null \
  && $C ps --format "table {{.Service}}\t{{.Status}}"'
