# Handoff: Build Run 2

Every Run 2 phase is built, tested and committed on `main`. Nothing was deployed. No accounts were created, and no real Google or email credentials were used: there is no local `.env`, so the one-off real Google sign-in check was skipped. Every Google call in the tests is mocked. Run 1's handoff is in git history (`6a820ca`).

## What was built

| Phase | What works | Not finished |
|---|---|---|
| Decisions | D2, D12, D25, D27, D28, D34, D51, D56 and D57 confirmed. MIT-0 is allowed: Vitest is back on jsdom and cffi is no longer pinned. Invites match **any** verified address on the account. Every export is audited, and the PIs get a notification and an email when someone else exports | – |
| A. Gaps | When someone loses project access (removed, demoted, removed from the lab or deactivated), their open tasks become unassigned. Each one gets an audit event, and the leads are notified. The handover report has an "Unassigned after access change" section. The database itself now enforces lab consistency: 16 composite foreign keys and 9 M2M triggers, with migrations that check existing data first. UI polish: plurals, relative dates with the full date on hover, the duplicate menu entry removed, and the sidebar becomes a drawer on small screens (Playwright checks at 390 px) | – |
| B. Google sign-in | allauth Google provider (openid, email and profile only). The button is hidden when it isn't configured. Users can add and verify extra email addresses, and connect or disconnect Google in Security settings. Sensitive account changes ask for the password again | Not tested against real Google |
| C. Email | `core/email.py`: sends through Celery after commit, retries temporary failures, and logs each send without the body. Text and HTML templates for verification, added-address confirmation, password reset, invite, ethics reminder, retention notice, export notice and general notifications. The provider is chosen by env vars (django-anymail) | No provider chosen |
| D. Integrations | A provider registry, `ConnectedAccount` and `ExternalLink`. Tokens are encrypted with MultiFernet, with key rotation (`manage.py rotate_integration_keys`). One HTTP client with host pinning, retries and refresh on 401. A generic OAuth2 flow with PKCE and state bound to user, lab and session. `manage_integrations` and `manage_lab_integrations` permissions. Accounts are revoked when a member leaves, plus a daily orphan sweep. The Integrations page has a Reconnect button. A token-leak test covers responses, logs, audit, admin, errors, the DEBUG 500 page and stored ciphertext | – |
| E. Google Drive | `drive.file` only, via the Google Picker, with incremental authorization and metadata only (never file contents). "Link from Google Drive" appears on Files and on dataset records, analyses, results and manuscripts. Refresh plus a daily job, showing "Changed since linked" and "No longer available". A Drive checksum fills an **empty** dataset checksum (D76). Drive links show on the lineage panel | Not tested against real Google. The CSP script paths for the Picker are unverified |
| F. Production | `backend/Dockerfile.prod` (gunicorn, non-root, health check) and `frontend/Dockerfile.prod`. `/healthz` checks the database and Valkey. `deploy/Caddyfile` (HTTPS, headers, CSP, body cap), `deploy/docker-compose.prod.yml`, `deploy/.env.prod.example`, a production settings checklist test, and `docs/DEPLOY.md` | Restore steps not rehearsed. Nothing deployed |

## How to run it

```
make dev            # start everything; app at http://localhost:5173
make seed           # fake pilot lab, now with two fake Drive links (run once, with dev running)
make test           # lint, backend, frontend, type drift, license check
make e2e            # Playwright (dev running and seeded)
make screenshots    # refresh docs/screenshots/
make types          # regenerate TypeScript types from the API schema
docker compose run --rm backend python manage.py migrate   # after pulling new migrations while dev is up
docker build -f backend/Dockerfile.prod backend            # production image
```

Seed logins are unchanged: `pi@`, `admin@`, `lead@`, `student@` and `viewer@` at `example.test`, with password `seed-password-not-secret`. If `make` isn't on your PATH, it lives under `%LOCALAPPDATA%\Microsoft\WinGet\Packages\ezwinports.make_*\bin\make.exe`.

## Test results

- **Backend:** 1,404 passed, 25 skipped in about 4.5 minutes. The skips are cross-lab swap cases for URLs that have no object ID.
- **Permission matrix:** 100% of endpoints, 98 endpoint rows across 9 personas, 984 cases including the cross-lab ID swap.
- **Frontend:** 132 Vitest tests and 13 Playwright tests (4 at mobile width). 35 screenshots.
- **Licenses:** 64 Python and 451 npm packages, all allowed.
- **Security reviews:** fresh opus reviews after Phases B, D and E found no cross-lab data path and no token leak.
  - They found 4 medium issues:
    - 1 after B: an attacker could get a victim to confirm the victim's address on the attacker's account. Fixed: an added address can only be confirmed while logged in as that account.
    - 2 after D: one user's disconnect could revoke another lab's shared Google grant, and a failed provider call could leave a removed member's account active.
    - 1 after E: the freshness check kept using a linker's token after they lost project access.
  - They also found 11 low issues, plus gaps in the token-leak test.
  - All are fixed, each with a regression test the fixing agent confirmed fails when the fix is reverted.

## Google redirect URIs and real-credential testing

Register these on the Google OAuth clients:
- **Sign-in:** `http://localhost:5173/accounts/google/login/callback/`
- **Integrations (Drive):** `http://localhost:5173/api/integrations/oauth/callback/`

Env vars, with placeholders in `.env.example`:
- **Sign-in:** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- **Drive:** `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET`, `GOOGLE_DRIVE_API_KEY` (browser key for the Picker), `GOOGLE_DRIVE_APP_ID` (the Cloud project number)
- **Token encryption:** `INTEGRATION_ENCRYPTION_KEYS`. Dev generates one if it's empty. Production refuses to start without it.

Steps:
1. Create a Google Cloud project and an OAuth consent screen in testing mode, with yourself as a test user.
2. Create the two OAuth clients and an API key, and enable the Drive API and the Picker API.
3. Put the values in a local `.env` (never commit it), then restart with `make dev`.
4. Follow `docs/MANUAL_TESTS.md` sections 2–10: sign-in, Drive hidden until configured, connect, pick and link, dataset version, refresh and change, delete and lose access, disconnect and lab removal. In the browser devtools, check that the Picker loads with no CSP errors.

## Email provider

Nothing is chosen. In dev, emails print in the Celery **worker** log (`docker compose logs worker`), not the backend log.
- **Postmark:** `EMAIL_BACKEND=anymail.backends.postmark.EmailBackend`, `POSTMARK_SERVER_TOKEN`, `DEFAULT_FROM_EMAIL`.
- **Amazon SES:** `EMAIL_BACKEND=anymail.backends.amazon_ses.EmailBackend`, `AWS_SES_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `DEFAULT_FROM_EMAIL`. SES reads the same AWS key pair as S3 file storage, so use an IAM user allowed both, or a role.
- **Either provider:** verify the sending domain (SPF and DKIM) with the provider first.

## Decisions a human should confirm

All are in `docs/DECISIONS.md`, marked **[H]**.
1. **D62.** If a Google address is already taken by an account it can't link to, nothing is created or linked, and the owner gets allauth's "account already exists" email.
2. **D73.** Google links to an existing account by email only for `@gmail.com`, or when Google's `hd` claim matches the domain. So a personal Google account using a university address must be connected from settings, not by signing in.
3. **D72.** An added address can only be confirmed while logged in as the account that added it.
4. **D74.** Re-authentication is required for email, Google and MFA changes. Accounts are capped at 5 addresses, and adding addresses is limited to 5 an hour.
5. **D71.** Every in-app notification is also emailed, including task assignment and unassignment. Confirm, or limit email to ethics, retention and export notices.
6. **D64, D66, D70.** Drive uses `drive.file` only, with its own OAuth client separate from sign-in. The Picker token is the one place an access token reaches the browser.
7. **D68.** Revoking at Google is skipped when another active connection (any user, any lab) shares the same Google account.
8. **D69.** Viewers may connect integration accounts, though they can't create links.

## Known issues, most severe first

1. **Never run against real Google or a real email provider.** Sign-in, the Drive OAuth flow, the Picker and the narrowed CSP script paths are all verified only with mocks.
2. **Production is untested in practice.** Both production images build and the settings checklist passes, but the stack has never run behind Caddy, and the backup restore steps in `DEPLOY.md` have never been rehearsed.
3. **Verification, reset and invite links pass through the Valkey broker as task arguments.** Production Valkey must have a password, and TLS if it isn't on a private network (`DEPLOY.md`).
4. **Downloads still stream through Django.** Each download holds a worker. The fix is X-Accel-Redirect or signed URLs.
5. **Deactivation side effects run only on a normal save.** Deactivating users with a bulk `QuerySet.update(is_active=False)` skips task unassignment and the immediate integration revoke. The daily orphan sweep still revokes the accounts. The admin and the app use normal saves.
6. **The database M2M triggers check links only when they're written.** They don't re-check if a parent's project changes later. No endpoint moves records between projects today.
7. **Run 1 leftovers:**
   - decision references can't be edited in the UI
   - there is no lab-wide search (D45)
   - watch `test_audit_api` for flakiness
   - in Vitest, the React Flow tests time out if workers aren't capped (now capped at 4)

## Next tasks, in priority order

1. Confirm or change the [H] decisions above.
2. Create the Google Cloud project and OAuth clients, then run `docs/MANUAL_TESTS.md` end to end.
3. Pick Postmark or SES, verify the domain, and send each email type once.
4. Stage a deployment from `deploy/`. Rehearse backup and restore, and check the CSP and the 50 MB upload cap in a real browser.
5. X-Accel-Redirect or signed-URL downloads.
6. The next integration on the framework (Microsoft OneDrive, then Overleaf, REDCap and Qualtrics).
7. Lab-wide search for the command palette.

## Agents used

18 subagents. None failed their checks twice, so no task was moved up a tier.
- **Opus:** 5 (Google sign-in linking, integration framework core, 3 security reviews)
- **Sonnet:** 10 (task unassignment, DB constraints, email service, sign-in UI, integration endpoints and UI, Drive, screenshots, 3 rounds of review fixes)
- **Haiku:** 3 (UI polish and jsdom, HTML email styling, production files)

One sonnet agent kept re-sending its finished report and was stopped. The orchestrator also made small integration fixes, all logged in `docs/PROGRESS.md`:
- the e2e signup now reads the link from the worker log
- the hardcoded product name became `PRODUCT_NAME`
- a duplicate D-number
- the Vitest worker cap
- the lint-test `.venv` walk
- the Drive icon
