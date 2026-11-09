# Deploying the research platform

This guide is for a first deployment. It covers one server running Docker, with Caddy in front
for HTTPS. Nothing here is automated: you run each step yourself.

The files are in `deploy/` and `backend/Dockerfile.prod`, `frontend/Dockerfile.prod`.
The development stack (`docker-compose.yml`) is separate and is not for production.

## The test server (2026-11-07)

`https://research.angadchahil.com` runs this stack for testing, with fake data only.

- **Host:** CanHost VPS (Canada), Ubuntu 24.04, 2 vCPU, 4 GB RAM plus 4 GB swap, 40 GB disk, IP `66.209.180.131`.
  - SSH login is user `angad` with a key only: password and root login are off.
  - The firewall allows 22, 80 and 443.
- **DNS:** an A record in Cloudflare, set to DNS only (grey cloud), so long assistant streams are not cut off at 100 s.
- **Code:** in `~/app`, copied from the committed `HEAD`. There's no git checkout and no GitHub credentials on the server.
- **Secrets:** generated on the server, in `~/app/deploy/.env.prod` (mode 600). `~/app/deploy/.env` holds only `SITE_DOMAIN`.
- **Set up (2026-11-07):**
  - **Email:** Postmark, sending as `noreply@angadchahil.com`. That domain is verified in Postmark; the `research.` subdomain is not, so sending from it is refused.
  - **Google:** sign-in and Drive, with separate OAuth clients in one Cloud project, plus the Picker API key.
- **Not set yet:**
  - **File bucket:** uploads go to the `labfiles` volume on the server.
  - **OneDrive, Dropbox, Box:** OAuth apps not created.
  - **Backups:** none.
  - **The audit-table role (section 7):** not applied.
- **Secrets go only in `~/app/deploy/.env.prod` on the server,** never in `.env.prod.example`. The example file is tracked by git.
- **Accounts:** the seed accounts (`pi@`, `admin@`, `lead@`, `student@` and `viewer@example.test`) have a random password set on the server, not the one in `seed_pilot.py`. The seed was loaded once with `run --rm -e DEBUG=True`.
- **Redeploy:** every push to `main` deploys through `.github/workflows/deploy.yml`, including migrations. Its `ci-deploy` SSH key is limited by a forced command in the server's `authorized_keys` to fetching `main` from GitHub and running `deploy/rebuild.sh`. To deploy something else by hand, commit it and run `sh deploy/push.sh`, which copies `HEAD` and runs the same rebuild.
- **Before real data goes on it:**
  - set up email
  - set up a bucket or backups
  - apply the audit role
  - remove the seed lab

## 1. What you need

- **A server** with Docker Engine and the Compose plugin. Two vCPU and 4 GB RAM is enough for a
  pilot. Open inbound ports 80 and 443 only. Do not expose 5432, 6379 or 8000.
- **A domain** (for example `research.example.org`) with an A record pointing at the server.
  Caddy obtains the certificate itself, so port 80 must be reachable at first start.
- **An S3-compatible bucket** for lab files (AWS S3, or another provider). Keep it private, turn
  on versioning, and create an access key that can only read and write that bucket.
- **An email provider**: Postmark or Amazon SES. Verify your sending domain with the provider
  first (SPF and DKIM records). Mail from an unverified domain is dropped.
- **A Google Cloud project** with two OAuth clients: one for sign-in, one for Drive. Use the
  redirect URIs listed in section 3.

## 2. Secrets and how to make them

Copy the template and edit the copy on the server:

```
cp deploy/.env.prod.example deploy/.env.prod
chmod 600 deploy/.env.prod
```

Never commit `deploy/.env.prod`. The repository's `.gitignore` lists it, but check
`git status` before any commit anyway.

Generate each secret once:

- **SECRET_KEY** (signs sessions and tokens):
  `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`
- **INTEGRATION_ENCRYPTION_KEYS** (Fernet keys that encrypt Google Drive tokens, D63). One key to
  start with:
  `docker run --rm research-backend:prod python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  Keys are comma-separated, newest first. See section 9 for rotation.
- **Database, Valkey and other passwords**:
  `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Use the same
  `VALKEY_PASSWORD` value in both the `VALKEY_PASSWORD` line and the two `redis://` URLs.

### Every variable in `.env.prod`

| Variable | What it is |
| --- | --- |
| `SECRET_KEY` | Django secret. The app refuses to start with a placeholder or missing value. |
| `DEBUG` | Must be `False`. Turns off the dev admin and schema routes. |
| `ALLOWED_HOSTS` | Your domain, no scheme, comma-separated if you have several. Never `*`. |
| `FRONTEND_URL` | `https://` plus your domain. Used in invite and verification links. |
| `CSRF_TRUSTED_ORIGINS` | `https://` plus your domain. Without it, form posts fail behind Caddy. |
| `TRUSTED_PROXY_COUNT` | `1` (Caddy). Controls which X-Forwarded-For address is trusted. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Database name, role and password. Used by the postgres container and the app. |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Leave as `postgres` and `5432` for this compose file. |
| `VALKEY_PASSWORD` | Password Valkey requires. Compose reads it at runtime. |
| `CELERY_BROKER_URL` | `redis://:<password>@valkey:6379/0`. Celery queue. |
| `CACHE_URL` | `redis://:<password>@valkey:6379/1`. Login and invite rate limits. |
| `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | Must be `True`. |
| `SECURE_HSTS_SECONDS` | `31536000`. Caddy sends the same header. |
| `SECURE_SSL_REDIRECT` | `False`. Caddy does the HTTP to HTTPS redirect. |
| `INTEGRATION_ENCRYPTION_KEYS` | Fernet keys (above). Startup fails without them. |
| `LAB_FILES_BUCKET` | Bucket name. Without it the app writes files to local disk, which is not for production. |
| `LAB_FILES_REGION` | Bucket region, for example `eu-west-1`. |
| `LAB_FILES_ENDPOINT_URL` | Empty for AWS. Set it for other S3-compatible providers. |
| `LAB_FILES_STREAM_DOWNLOADS` | Leave empty. PDFs always stream through Django and other files redirect to a 60 second presigned URL (D90, D123). `True` streams everything; use it only if your provider ignores response header overrides. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Credentials for the bucket. The app also reads them for SES. |
| `DEFAULT_FROM_EMAIL` | Sender, for example `Research Platform <noreply@your-domain>`. |
| `EMAIL_BACKEND` | `anymail.backends.postmark.EmailBackend` or `anymail.backends.amazon_ses.EmailBackend`. |
| `POSTMARK_SERVER_TOKEN` | Postmark server token (Postmark only). |
| `AWS_SES_REGION_NAME` | SES region, for example `eu-west-1` (SES only). |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in client. Empty hides the Google button. |
| `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET` | Google Drive integration client (separate, D66). |
| `GOOGLE_DRIVE_API_KEY`, `GOOGLE_DRIVE_APP_ID` | Google Picker browser API key and Cloud project number. Empty hides the Drive actions. |

If you use SES, comment out the Postmark lines and uncomment the two SES lines in the template.

### Google OAuth redirect URIs

Register these in Google Cloud, using your real domain:

- Sign-in client: `https://<domain>/accounts/google/login/callback/`
- Drive client: `https://<domain>/api/integrations/oauth/callback/`

### Checking the file before you start

The settings test in `backend/core/tests/test_production_settings.py` checks the template with
dummy values. To check your real file, run the same checks by hand after step 4:

```
docker compose -f deploy/docker-compose.prod.yml run --rm backend python manage.py check --deploy
```

## 3. Build the images

From the repository root:

```
docker build -f backend/Dockerfile.prod -t research-backend:prod backend
docker build -f frontend/Dockerfile.prod -t research-frontend:prod frontend
```

Or, from `deploy/`, `docker compose -f docker-compose.prod.yml build`, which builds both and
tags the backend image as `research-backend:prod` for the worker and beat services.

The backend image runs gunicorn as a non-root user and checks `/healthz` every 30 seconds. The
frontend image is a static build served by Caddy.

### Lab file downloads (D90, D123)

Downloads check access in Django first. What happens next depends on the file:

- **PDFs (shown inline by the viewer) stream through Django**, with `nosniff` and
  `Content-Security-Policy: sandbox`. A bucket URL cannot carry those headers, so anything shown
  inline never gets one.
- **Everything else redirects (302) to a presigned bucket URL** that lasts 60 seconds and forces
  `Content-Disposition: attachment`.
- Every new object is also written with `Content-Type: application/octet-stream`,
  `Content-Disposition: attachment` and `Cache-Control: private, no-store` as object metadata
  (`documents.storage.LabFilesS3Storage`). A provider that ignores the `response-*` overrides
  therefore still serves a download, never a page on the bucket origin.

What you must do:

1. **Keep the bucket private** and serve nothing else from it. No bucket CORS rule and no bucket
   entry in the Caddy `connect-src` are needed any more: the viewer reads PDFs from the app
   origin, and other files are plain downloads. (Earlier versions needed both; you may remove
   them. Leaving them does no harm.)
2. **Objects uploaded before this change** (D90 era) lack the metadata. Rewrite it once, for
   example `aws s3 cp s3://BUCKET/labs/ s3://BUCKET/labs/ --recursive --metadata-directive
   REPLACE --content-type application/octet-stream --content-disposition attachment
   --cache-control "private, no-store"` (on a versioned bucket this adds versions). Until then they
   rely on the presigned URL's overrides alone.

`LAB_FILES_STREAM_DOWNLOADS=True` streams everything through Django, for a provider that ignores
`response-content-disposition`.

## 4. First start

Run these from `deploy/`:

```
docker compose -f docker-compose.prod.yml up -d postgres valkey
docker compose -f docker-compose.prod.yml run --rm backend python manage.py migrate
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
curl -s https://<domain>/healthz
```

`/healthz` returns `{"status":"ok"}` when the database and Valkey both answer. A 503 names the
failing check (`database` or `valkey`) and nothing else. Check the logs with
`docker compose -f docker-compose.prod.yml logs backend` if it does not.

Migrations are a separate step, so a bad migration never runs on container restart.

## 5. Create the first user and lab

There is no separate admin account. The first user is created the normal way:

1. Open `https://<domain>/` and sign up with your email address (or sign in with Google).
2. Verify the email address through the link the provider sends. Sign-up is blocked until you do.
3. In the app, create a lab. The account that creates a lab becomes its PI.
4. Invite the other members from the lab's members page. Invites are throttled per lab (D50).

Lab creation is throttled to 5 a day per user.

## 6. Start Celery and the scheduled jobs

`worker` runs background jobs (email, retention scans, ethics reminders). `beat` schedules the
daily jobs. Both are started by `up -d` in step 4. Check them with
`docker compose -f docker-compose.prod.yml logs worker beat`. Email does not send unless the
worker is running.

## 7. The audit table role (D23)

Audit events are append-only. The database trigger rejects UPDATE, DELETE and TRUNCATE, and
production must also give the app role only INSERT and SELECT on `audit_auditevent`. Migrations
do not do this, because migrations run as the table owner.

Create an application role that does not own the tables, and then run, as the owner:

```
-- as the owner who runs migrations
REVOKE ALL ON audit_auditevent FROM research_app;
GRANT SELECT, INSERT ON audit_auditevent TO research_app;
GRANT USAGE, SELECT ON SEQUENCE audit_auditevent_id_seq TO research_app;
```

The app then connects as `research_app` (set `POSTGRES_USER` to it). The migration role is a
separate user that you keep for `migrate` runs. Check it with `\dp audit_auditevent` in psql.

## 8. Backups

Three things must be backed up, and they fail independently.

1. **The database.** Run `pg_dump` every night from cron on the host, and keep 14 daily and 8 weekly
   copies:

   ```
   docker compose -f /srv/research/deploy/docker-compose.prod.yml exec -T postgres \
     pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > /backups/research-$(date +%F).dump
   ```

   Copy the dump off the server (a second provider or a bucket with a different account). A
   backup on the same disk is not a backup.
2. **The lab files bucket.** Keep versioning on, and sync the bucket to a second location on a
   schedule (for example `aws s3 sync` to another region). The database has only the file keys,
   not the file contents.
3. **The encryption and signing keys.** Store `SECRET_KEY` and every value in
   `INTEGRATION_ENCRYPTION_KEYS` in a password manager, kept apart from the database backups.
   Without the Fernet keys, the Drive tokens in a database dump are useless, and a restored
   database cannot decrypt them. Without `SECRET_KEY`, every existing session is invalid.

Do not store the `.env.prod` file inside a backup you share with anyone who should not hold the
keys.

### Restore, in order

Use this on a fresh server or after losing the database volume. These steps have not been
rehearsed on a real server yet. Run them on a spare server before you rely on them.

1. Install Docker and copy `deploy/` onto the server.
2. Put back `deploy/.env.prod` with the same `SECRET_KEY`, `INTEGRATION_ENCRYPTION_KEYS` and
   `POSTGRES_*` values as before. Changed keys break logins or stored tokens.
3. Build the images (step 3).
4. Start the database only: `docker compose -f docker-compose.prod.yml up -d postgres`.
5. Copy the dump in and restore it:

   ```
   docker compose -f docker-compose.prod.yml cp research-2026-01-01.dump postgres:/tmp/restore.dump
   docker compose -f docker-compose.prod.yml exec postgres \
     pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists /tmp/restore.dump
   ```

   Run the restore as the owner role, not `research_app`, so tables and the audit grants come back
   correctly. Then reapply the grants in section 7.
6. Start Valkey and the app: `docker compose -f docker-compose.prod.yml up -d`. Valkey holds only
   queued jobs and rate-limit counters, so it does not need restoring.
7. Run `migrate` (a no-op if the dump is current).
8. Check `https://<domain>/healthz`, sign in as a known user, and open a lab's attachment to confirm
   the bucket is reachable.

## 9. Key rotation

Rotate the Fernet keys (D63) when a key may have leaked, or on a set schedule.

1. Generate a new key (section 2).
2. Put it first in `INTEGRATION_ENCRYPTION_KEYS`, with the old key after it:
   `NEW,OLD`. Restart the backend and worker so both load it:
   `docker compose -f docker-compose.prod.yml up -d backend worker`.
3. Re-encrypt every stored token under the new key:
   `docker compose -f docker-compose.prod.yml run --rm backend python manage.py rotate_integration_keys`
4. Only after step 3 succeeds, remove the old key and restart the backend and worker.

Do not remove the old key before step 3. Those tokens could not be read again.

## 10. Valkey: password and TLS

Valkey carries Celery jobs. Those jobs include the links for email verification, password reset
and invites. Anyone who can read the queue can read those links.

- **The password is required.** The compose file starts Valkey with `--requirepass`. Do not run it
  without one.
- **On the private compose network, plain `redis://` is acceptable.** Nothing else can reach the
  container, because no port is published.
- **If Valkey is ever reachable across a network you do not control** (a separate host, a managed
  service, a second server), use TLS: `rediss://` in `CELERY_BROKER_URL` and `CACHE_URL`, with a
  Valkey build configured for TLS. Do not expose the plain port to the internet at any point.

## 11. Email providers

- **Postmark.** Set `EMAIL_BACKEND=anymail.backends.postmark.EmailBackend` and
  `POSTMARK_SERVER_TOKEN` (a server token, not the account token). Verify the sender domain in
  Postmark first.
- **Amazon SES.** Set `EMAIL_BACKEND=anymail.backends.amazon_ses.EmailBackend`, and
  `AWS_SES_REGION_NAME`. The app uses `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` for SES. Use
  a key that can only send email. SES starts in sandbox mode, so request production access before
  inviting real users.

Send one test sign-up to a real inbox and confirm the link works before you invite anyone.

## 12. Upgrading

1. Take a database backup (section 8, step 1).
2. Pull the new code, rebuild the images, and run `migrate` as in step 4.
3. Run `docker compose -f docker-compose.prod.yml up -d`.
4. Check `/healthz` and the logs.

To go back, restore the backup from before the upgrade. Migrations are not reversed
automatically.

## Content-Security-Policy and the Google Picker
`script-src` in `deploy/Caddyfile` names the Picker's script paths (`apis.google.com/js/api.js`, `apis.google.com/_/scs/`, `www.gstatic.com/_/`), not whole Google hosts (D78). Google changes the paths it loads, and they could not be confirmed offline. Before go-live, open the Picker in a real browser with real Drive credentials, watch the console for CSP violations, and widen only the exact path reported.
