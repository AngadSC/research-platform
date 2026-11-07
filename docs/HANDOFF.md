# Handoff

**Test server (2026-11-07):** `https://research.angadchahil.com`. Setup, limits and how to redeploy are at the top of `docs/DEPLOY.md`.

## Run 5: SSO, bring-your-own AI, PI dashboard, training, data management (2026-11-05)

Built, tested, reviewed and pushed. **Full notes, every issue and every design choice are in `docs/RUN5_NOTES.md`.** Decisions are D152–D204 in `docs/DECISIONS.md`. Nothing has touched a real university sign-in server, a real Claude or ChatGPT connector, or a real API key.

### What's new

| Feature | What works | What you need to do |
|---|---|---|
| **University sign-in (SAML)** | Email-first login: a `@ualberta.ca` address gets "Continue with University of Alberta". Signed assertions are required, and only verified addresses on the institution's own domains link to existing accounts. An optional "require SSO" setting can block password sign-in for that domain (off by default). Config is a superuser-only `InstitutionSSO` record, set with `manage.py configure_sso` | Send UAlberta IT our SP metadata (the exact request is in `docs/MANUAL_TESTS.md` and `RUN5_NOTES.md`). Before go-live, add their IdP host to the Caddyfile CSP `form-action` (D158) |
| **Your own Claude or ChatGPT (MCP connector)** | Our app is a remote MCP server at `<site>/mcp`. Add it in claude.ai (Pro, Max, Team or Enterprise) under **Customize > Connectors > Add custom connector**, so **your subscription pays for the AI**. OAuth sign-in, with consent defaulting to **one lab and read-only**. Personal access tokens for Claude Code (this works on localhost today). Every call is re-checked against your current roles. Write tools are audited. Revoke in Settings > Connected AI apps; PIs can revoke access to their lab | claude.ai and ChatGPT need a public https address (a deployment, or a tunnel you set up). ChatGPT connectors are documented for **Business, Enterprise and Edu**; Plus and Pro are unconfirmed (D169) |
| **In-app assistant (your own API key)** | A chat panel scoped to your lab or project. **Claude via your Anthropic key:** Opus 5.5 by default, or Sonnet 5.5 or Haiku 5.5; adaptive thinking; Anthropic's server-side fallback for declined requests is on by default and can be turned off. **GPT via your OpenAI key:** this adapter has never touched the live API. Write actions need you to click **Approve**, and the dialog shows names and the exact text. Token usage shows on every message. Keys are encrypted and only the last 4 characters are ever shown | Paste a key in Settings > AI and try it. API usage is billed to that key, separately from any Pro or Plus subscription |
| **Lab AI switch** (Settings > AI) | PI or lab admin chooses **Off / MCP only / MCP + in-app** for the lab (default MCP + in-app, with a notice). Enforced on both paths | Decide the default for labs with participant data (D188) |
| **PI dashboard** | The PI's and lab admin's landing page: overdue tasks, ethics and funding expiring, stalled projects, missing data management plans, expiring training, a project health table, and per-person counts (counts only, no activity timeline) | – |
| **Training and certifications** | Required trainings, private member records with certificates, a compliance matrix in Admin, My training, reminders at 60, 30 and 7 days and on expiry (emailed, D178), and a weekly digest for the PI | Add your lab's real requirements, e.g. TCPS 2 CORE or WHMIS |
| **Data management plans** | One per project, in Workflow > Data, with Tri-Agency sections, status, history and lead approval | – |
| **Borealis and FRDR** | Link published datasets by DOI or URL, metadata only. The FRDR and Borealis DOIs were checked live through DataCite | Borealis' own API was down for maintenance and is unverified (D180–D186) |

### Security review (fresh opus) and fixes

- **Nothing critical or high.** No cross-lab path in the permission code, no token or key leak, no SSRF.
- **4 medium issues, all fixed (D193–D199):**
  - Redirect URIs are now matched exactly.
  - Consent and new tokens need a recent sign-in, and every AI grant is revoked on a password change, an MFA change or deactivation.
  - The assistant has a server-wide stream cap and a 300-second deadline.
  - Prompt-injection defences: record text is labelled as untrusted to the AI, consent defaults to one lab and read-only, the approval dialog shows names, and links point only to the app's own origin.
- **4 low issues, all fixed (D200–D203):**
  - the unsigned SAML logout route is removed
  - require-SSO can't be bypassed through another verified address
  - the grant list for a lab no longer shows a member's other labs
  - unused app registrations are pruned
- **Residual risk (D199):** text a lab member writes could try to steer another member's AI. In-app writes need your approval. Over MCP, your Claude or ChatGPT's own confirmation prompt is the last guard.

### Tests

- **Backend:** 3,262 passed, 97 skipped, 0 failed. One inventory test flaked once and passed on rerun.
- **Frontend:** 267 Vitest pass. Lint, types and licences are clean: 83 Python packages, including `anthropic` (MIT), `openai` (Apache-2.0), `python3-saml`/`xmlsec` (MIT) and `lxml` (BSD), and 451 npm packages.

### Decisions to look at

- **D188:** AI is allowed by default per lab.
- **D193 and D169:** the exact Claude and ChatGPT callback URLs came from documentation, not live traffic.
- **D196:** the stream cap is 10 of 24 threads.
- **D199:** the residual prompt-injection risk.
- **D202:** require-SSO looks at all of a person's verified addresses.
- **D153–D155, D158:** SSO configuration and production prerequisites.

### How to try it today

1. Restart the stack (`docker compose restart backend worker frontend`), then run `migrate` and `make seed`.
2. As `pi@` (password `seed-password-not-secret`), you land on the Dashboard. Then visit:
   - Admin > Training
   - Settings > AI, for the lab's AI policy
   - a project's Workflow > Data, for the data management plan
3. **Assistant:** go to Settings > AI, paste an Anthropic key, open the assistant, and ask "What's overdue?".
4. **Claude Code:** go to Settings > Access tokens, create one, then run the `claude mcp add` command the page shows. Ask "List my labs".
5. **SSO:** test against a local test IdP, as described in `docs/MANUAL_TESTS.md`. The dev database has a fake SSO institution, `sso.example.test`, enabled for screenshot 61. It's harmless, since no real IdP answers for it; turn it off with `configure_sso` or in the Django admin if it gets in the way.

Screenshots 58–67 show the new screens. Browser tests: 24 of 24 pass; the Overleaf paste spec is occasionally flaky under load.

## Run 4: founder's change list (2026-11-05)

Built, tested and pushed. Decisions are D125–D151 in `docs/DECISIONS.md`, and limitations are below. Screenshots 44–57 show the new screens.

- **Look:** white base with high-contrast red, green, amber and indigo buttons, status badges and tabs (one shared `TabNav`). Dark mode has a header toggle saved to your account. The board colours are yellow To do, orange In progress and green Done.
- **Landing page:** a product page at `/` with Sign in and Register at the top right.
- **Search:** Ctrl/Cmd+F (and Ctrl/Cmd+K) opens search. Inside text fields, documents and PDFs, Ctrl+F stays the browser's own find.
- **Unread badges** on Notifications, the lab entry and the bell.
- **Project Workflow tab:** Funding, Ethics (approvals linked to the project, plus University of Alberta resources), Participants (counts only, no personal data), Data, Analysis, Manuscript and Review. Ethics left the sidebar; the lab-wide list is in Admin.
- **Overview:** high, medium and low deadline priorities, and "Last edited … by …".
- **Tasks:**
  - a detail drawer with assignee and status
  - attached documents and files
  - a task thread
  - the board is the default; switch to list in Settings or on the toggle
- **Admin tab** (PI and lab admin): lab details, the onboarding checklist, inventory with CSV export, institution resources, and links to the audit log, retention and ethics.
- **Settings:** one page for profile, appearance, default task view, notifications, security and integrations.
- **Not built:** email inbox connection (D126; a per-project forwarding address is the cheaper option if you want it) and true real-time co-editing (D145; documents auto-refresh instead).
- **Tests:**
  - backend: 2,541 passed, 66 skipped
  - permission matrix: 1,404 cases
  - Vitest: 212
  - Playwright: 23, with the Overleaf spec flaky once
  - lint, types and licenses: clean
- **Database:** the dev database is local Postgres in Docker on this PC (volume `research-platform_pgdata`), not hosted anywhere.

## Run 4 limitations

Each agent adds its own bullets here.

- **Admin: University of Alberta starter links are incomplete (D149).** Verified and included (each fetched and confirmed official): Research Ethics Office, ARISE support page, Internal research funding, Institutional approval for grant applications (Research Administrative Services), Institutional Research Data Management Strategy. Gaps, left out because no official page was confirmed: a Tri-Agency (NSERC, SSHRC, CIHR) guidance page on a ualberta.ca address; the library's research data management page (it redirects to a doubled-slash address, so I did not trust it); the DMP Assistant; a page listing all the REBs. The Research Services Office is also called Research Administrative Services on the site. Add them in Admin > Institution resources.
- **Admin: onboarding has links only, no file attachments, and only pi and lab_admin tick items (D148).** Members cannot see or tick their own checklist.
- **Admin: the institution is chosen by typing a name (D146).** Anyone with manage_lab can create a new Institution row; there is no merge or rename, and a misspelled name creates a separate institution. Starter links apply only to the exact name "University of Alberta" (other casings are corrected).
- **Admin: institution resources are per lab (D149).** Changing the institution later does not remove links already copied. Starter updates are not pushed to labs that already have them; re-run `load_institution_resources` to add new starters.
- **Admin: members can edit inventory (D147).** If the founder wants only pi and lab_admin, remove `manage_inventory` from the member row in `core/permissions.py`, the matrix rows and `canEdit` in the UI.
- **Settings: notification choices are read-only (D150), and Settings uses the first lab for its Integrations and Admin links.** `/settings` is outside a lab, so the sidebar shows no lab entries there (same as the old Account page).
- **Admin lists and the inventory CSV export are unpaginated.** Fine for a lab-sized list; add paging if one lab holds thousands of items.

- **Tasks: documents are not co-edited in real time (D145).** Open documents poll every 5 seconds and show "<name> updated this document" with a Reload button when someone else saves. Real simultaneous editing needs a websocket and CRDT service (Yjs plus channels or y-websocket) that this stack does not have. Two people editing at once still get the conflict dialog on the second save; edits are not merged.
- **Tasks: the thread and a task's documents and files are polled, not pushed.** The thread refreshes every 10 seconds while the drawer is open; the task list refreshes on actions and focus. A new document or upload from a task is two requests, so a failure in the second leaves the document or file in the project but not on the task.
- **Tasks: viewers cannot post (D142).** Posting needs `edit_content`. If the founder wants viewers to comment, change `perms["POST"]` on `TaskPostListCreateView`, the matrix rows and the composer's `canPost`.
- **Tasks: board colours are fixed light surfaces in both themes (D144)** because the theme tokens have no orange; they will not follow later theme changes.
- **Tasks: post edits are not audited, and an edit does not re-notify the assignee.**
- **Workflow: deletes do not move "Last edited" (D139).** Only saves are stamped; removing a task or record leaves the line as it was. Add a `post_delete` receiver if that should count.
- **Workflow: participant privacy is a warning plus one guard (D136).** The server refuses email addresses in recruitment notes, but names, initials, phone numbers and participant ids cannot be detected, so the warning text is the real control. Notes on entries and the plan are visible to everyone who can view the project.
- **Workflow: recruitment counts are increments, not a ledger of transitions (D136).** Withdrawing someone does not reduce Enrolled; enter it as a Withdrawn entry. Entries can be removed but not edited in the UI (the API allows PATCH).
- **Workflow: funding amounts are lead-only (D133).** A contributor or viewer sees the record without the amount; the PI and lab admin see all (implicit leads). Search never matches amounts. If the founder wants contributors to see amounts, drop the check in `provenance/serializers.py` (`FundingSerializer`) and `provenance/services.py` (`FUNDING_LEAD_ONLY`).
- **Workflow: no reviewer notification and no sign-off enforcement (D138).** Setting a review to approved does not block or unlock anything; the reviewer is not told. Holder and reviewer pickers list all lab members and the server rejects anyone who cannot see the project.
- **Workflow: the lab-wide ethics list left the sidebar (D134).** It lives in Admin and behind a link in Workflow > Ethics (pi and lab_admin only). A plain member can reach an approval only through a project or a notification.
- **Workflow: the Ethics tab creates approvals but not files (D134).** Upload the approval letter from the approval's own page after saving.
- **Workflow: institution links are shown only if the lab has them (D135).** An empty list or an error draws nothing, so a lab that never loaded resources sees no "Ethics resources" box.
- **Workflow: old `/research` addresses redirect, but emailed or saved deep links to `/ethics` from the sidebar era are unchanged and still work.** The Playwright and Vitest suites use the new addresses.

## Morning summary: Run 3 (overnight, 2026-11-04 to 05)

Everything below is built, tested against mocks, committed on `main` and pushed. Nothing was deployed, no accounts were created, and no real credentials were used. **No integration has ever talked to its real service**, so your hand test today is the first real contact. Every decision I made on my own is in `docs/DECISIONS.md` under "Run 3" (D79 to D124). The ones you should look at are listed below.

### What's new

| Area | What works | Where to look |
|---|---|---|
| Email noise (your call on D71) | Only ethics expiry, retention due, project exported and integration-problem notices are emailed. Task assignment, unassignment and invite-accepted notices are in-app only. Account emails (verification, reset, invites) always send | Notifications bell vs. worker log |
| Integrations framework v2 | One file per provider. Four auth types: OAuth, API key, link-only and public. Self-hosted instance URLs (REDCap, GitLab) with SSRF defences: https/443 only, private and metadata IPs refused, DNS pinned per request, redirects stay on host. Every outside call has a total deadline and a 2 MB cap. Keys are encrypted like tokens and never shown back | Lab settings > Integrations |
| 13 new providers | **File storage:** OneDrive/SharePoint, Dropbox, Box (OAuth). **Code:** GitHub and GitLab (read-only access tokens). Linking a commit fills an analysis' repo and commit if both are empty. **Writing:** Overleaf (link-only; share links are refused). **Data capture:** REDCap, Qualtrics, protocols.io (API keys; **project and survey metadata only, never records or responses**). **References:** Zotero (read-only key; adds the item to a decision's references). **Repositories:** Zenodo, Figshare (public, no account), OSF (read-only token) | "Link from…" on Files, datasets, analyses, results, manuscripts, decisions and documents |
| Generic integrations UI | The Integrations page and every "Link from…" menu are built from the provider list: connect dialogs per auth type, search with live results, paste a URL, or the Google Picker | Screenshots 27 and 36–43 |
| Lab-wide search | Ctrl/Cmd+F or Ctrl/Cmd+K searches projects, tasks, document text, research records, ethics approvals and linked items. Each hit is permission-checked (restricted approvals stay hidden) | Command palette |
| Decision references | Add, remove and reorder references (title, URL, DOI) on decisions, with validation | Research > Decisions |
| Downloads | With S3 storage, non-PDF downloads redirect to a 60-second signed link after the same permission check and audit. PDFs still stream through the server so they keep the sandbox headers. The bucket needs a CORS rule (`DEPLOY.md`) | `documents/views.py` |

Not built, and why (D79): LabArchives and Benchling (vendor-issued keys, no way to test), ORCID (an identity, not lab data), Slack/Teams (not research records), and billing (needs a payment account and pricing).

### Tests (final gate, all green)

- **Backend:** 2,098 passed, 59 skipped in about 6.5 minutes. Permission matrix: 100 endpoint rows, 1,004 cases, 100% coverage.
- **Integrations alone:** about 740 tests: a shared contract test per provider, 86+ SSRF tests including DNS rebinding, slow-drip and oversize response tests, the token and key leak test, and a check that no provider has a download path.
- **Frontend:** 153 Vitest, 15 Playwright, 43 screenshots. Licenses: 64 Python and 451 npm packages, all allowed.
- **Security review** (fresh opus, all of Run 3) found no cross-lab path, no token or key leak, no SSRF to internal addresses and no participant-data path. It found one medium-high issue: slow or huge responses from a user-chosen server could tie up every worker. Also 3 low issues: a repo/commit mismatch, a reference-append race, and PDF headers on signed links. All are fixed, with regression tests checked to fail when the fix is reverted.

### Decisions to check this morning

1. **D81:** lab **viewers** may connect integration accounts, including API keys, although they can't create links. Easy to tighten to members and above.
2. **D106:** GitHub uses a pasted fine-grained read-only token, not "Sign in with GitHub", because GitHub OAuth has no read-only scope for private repos.
3. **D108:** GitLab uses a `read_api` token, plus the server address (type `gitlab.com` for the hosted one).
4. **D109:** Overleaf accepts only `overleaf.com/project/<id>` links. Share links are refused because anyone holding one gets access.
5. **D100:** OneDrive asks for `Files.Read.All` (read-only), so SharePoint and shared files work. `Files.Read` would reach only your own OneDrive.
6. **D110:** REDCap reads only project info, not the data dictionary.
7. **D82:** set `INTEGRATION_ALLOWED_INSTANCE_HOSTS` in production if you want self-hosted servers limited to your university's domains.
8. **D115, D118:** Zotero refuses write-capable keys, and OSF uses a token so private projects work.
9. Still open from Run 2: D62, D64, D66, D68–D70 and D72–D74 (Google sign-in and Drive details).

### Testing by hand today

1. `make dev`, then `docker compose run --rm backend python manage.py migrate` and `make seed`. The seed now includes fake GitHub, Overleaf, Zotero and Zenodo links.
2. **No credentials needed:**
   - Lab-wide search (Ctrl+K).
   - Editing decision references.
   - Pasting a real public **Zenodo** or **Figshare** URL onto a dataset. These are the first real outside calls and need no account.
   - Pasting an **Overleaf** project link onto a manuscript.
3. **With a free token:** GitHub (fine-grained, read-only), GitLab, Zotero, OSF and protocols.io. Paste the token in Integrations > Connect, then link from an analysis, decision or dataset.
4. **Needs an app registration:** Google sign-in and Drive, OneDrive, Dropbox and Box. Put the client ID and secret in `.env` (names below) and restart.
5. **Needs a university account:** REDCap and Qualtrics.
6. `docs/MANUAL_TESTS.md` has setup steps and checks for every provider. Expect some field-name mismatches against the real APIs. Several reply shapes were written from documentation only, and are flagged in their decisions.

OAuth redirect URI for every integration: `http://localhost:5173/api/integrations/oauth/callback/`. Google sign-in: `http://localhost:5173/accounts/google/login/callback/`.

New env vars, with placeholders in `.env.example`:
- `INTEGRATION_ONEDRIVE_CLIENT_ID`, `_SECRET` and `INTEGRATION_ONEDRIVE_TENANT` (default `common`)
- `INTEGRATION_DROPBOX_CLIENT_ID` and `_SECRET`
- `INTEGRATION_BOX_CLIENT_ID` and `_SECRET`
- optional: `INTEGRATION_ALLOWED_INSTANCE_HOSTS` and `LAB_FILES_STREAM_DOWNLOADS`

API-key providers need no env vars; users paste their own token.

### Known issues, most severe first

1. **No provider has been run against its real API.** Mocks follow the published docs, and some reply shapes are guesses: Qualtrics metadata, protocols.io v4, and OSF file ids are flagged.
2. **Production is still untested in practice:** no real deploy, the restore drill never rehearsed, the CSP and bucket CORS never checked in a browser. Valkey must have a password and TLS (`DEPLOY.md`).
3. **The machine struggled under parallel test runs tonight.** Postgres crash-looped once under seven concurrent test containers and recovered after a restart. A separate container, `smart-home-platform-1`, was also running and at one point crash-looping, competing for resources. One run at a time is fine: the full suite takes about 6.5 minutes.
4. **Two Playwright specs can time out right after a backend restart.** They pass on a rerun, and the timeouts were raised.
5. Unchanged from Run 2: bulk `QuerySet.update(is_active=False)` skips the immediate deactivation side effects (the daily sweep still revokes integrations), and the M2M database triggers don't re-check links if a record moves between projects later.

### Next tasks, in priority order

1. Hand test as above, starting with the no-credential providers. Then answer D81 and the Run 2 decisions still open.
2. Register OAuth apps (Google, Microsoft, Dropbox, Box) in test mode and run `docs/MANUAL_TESTS.md`.
3. Pick an email provider (Postmark or SES) and send one of each email.
4. Stage a deployment from `deploy/`, and rehearse backup and restore.
5. Fix whatever the real APIs disagree with. Each provider is one file, plus its test's mocked replies.
6. Later: billing, ORCID sign-in, LabArchives or Benchling if a lab asks.

### Agents used tonight

12 subagents, no escalations. The review-fix task was briefed at sonnet high from the start, because it combined a DoS fix with concurrency changes.
- **Opus:** 2 (framework v2, security review)
- **Sonnet:** 10 (downloads, search, UI, 4 provider batches, verifier, review fixes, screenshots)

Four agents were stopped after they finished but kept re-sending their reports. The provider agents lost test time to the Postgres crash, so a verifier ran every provider's tests one at a time and fixed 21 failures. Full log: `docs/PROGRESS.md`.

---

# Run 2 handoff (previous)


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
