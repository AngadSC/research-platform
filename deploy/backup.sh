#!/usr/bin/env bash
# Nightly backup to the bucket named by BACKUP_BUCKET in .env.prod (docs/DEPLOY.md section 8).
# It does nothing until BACKUP_BUCKET is set, so the cron line can go in before the bucket exists.
# Cron, as the deploy user:  30 3 * * * bash ~/app/deploy/backup.sh >> ~/backup.log 2>&1
set -euo pipefail
cd "$HOME/app/deploy"
if ! grep -q '^BACKUP_BUCKET=.' .env.prod; then
  echo "$(date -Is) BACKUP_BUCKET not set, skipped"
  exit 0
fi
C="docker compose -f docker-compose.prod.yml"
day=$(date +%F)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Dump to a file first: a dump that fails halfway is never uploaded.
$C exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > "$tmp/db.dump"
$C exec -T backend python manage.py backup_upload "db-$day.dump" < "$tmp/db.dump"

# Lab files on local disk are copied too. Once they live in a bucket, its versioning covers them.
if ! grep -q '^LAB_FILES_BUCKET=.' .env.prod; then
  $C exec -T backend tar -czf - -C /data/lab_files . > "$tmp/files.tar.gz"
  $C exec -T backend python manage.py backup_upload "files-$day.tar.gz" < "$tmp/files.tar.gz"
fi

# Optional heartbeat (for example healthchecks.io): it alerts you when a night is missed.
ping=$(grep '^BACKUP_PING_URL=' .env.prod | cut -d= -f2- || true)
if [ -n "$ping" ]; then curl -fsS -m 10 "$ping" > /dev/null; fi
echo "$(date -Is) backup ok"
