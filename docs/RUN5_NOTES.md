# Run 5 notes: SSO, AI connectors, PI dashboard, training, data management

The founder asked for detailed notes of everything done, every issue hit and every design choice. Each agent appends its own section below. Decisions also go in `docs/DECISIONS.md` under "Run 5".

## Orchestrator: scope and the AI question (2026-11-05)

- **Can users plug in their Claude Pro or ChatGPT Plus subscription?** Not into our app. Consumer subscriptions work only inside claude.ai or chatgpt.com, and API access is billed separately. What does work is the reverse: we expose the lab app as a **remote MCP server**, and the user adds it as a custom connector in their own Claude (Pro, Max, Team or Enterprise). Their subscription then pays for the AI, and our app only answers permission-checked tool calls. ChatGPT supports MCP connectors on some plans; the MCP agent checks the details.
- **Second path:** an in-app assistant where each user pastes their own Anthropic or OpenAI **API key** (pay as you go, encrypted at rest like integration keys).
- **Shared tool layer:** both paths use one set of permission-scoped tools, so the AI can never see more than the user can.
- **Waves:**
  - Wave 1: SSO (opus), MCP server and tool layer (opus), PI dashboard (sonnet), training and certifications (sonnet).
  - Wave 2: data management plans plus Borealis/FRDR (sonnet), in-app bring-your-own-key assistant (sonnet).
  - Then a security review, fixes, screenshots and a push.
- **Postgres rule:** one test container per agent, scoped tests only. The orchestrator runs the full suite.


## PI dashboard (sonnet agent, D170-D174)

**What was built**
- Backend `labs/dashboard.py`, route `GET /api/labs/<lab>/dashboard/` (name `labs:dashboard`), documented in the OpenAPI schema (serializers there are for the schema only; the view returns a dict built by `build_dashboard`). Sections: `summary` (tile numbers), `projects` (one row each), `attention` (seven `{total, items}` lists), `people`.
- Frontend: `pages/DashboardPage.tsx` (page plus `LabIndexPage`, the lab landing switch), `hooks/dashboard.ts`, `lib/dashboard.ts` (date helpers and project sorting), sidebar entry in `lib/nav.ts`, routes in `routes.tsx`.
- Tests: `labs/tests/test_dashboard.py` (13), a hand-written row in `tests/test_permission_matrix.py`, `pages/DashboardPage.test.tsx` (6), `e2e/dashboard.spec.ts`.
- Types regenerated with the two commands under `types:` in the Makefile.

**Design choices and why**
- *Access:* reuse `manage_lab` instead of a new permission (same reason as D146). The query layer is still `visible_to` so a future role change cannot widen what is shown.
- *Queries:* one grouped aggregate for task counts per project, one for per-person counts, `DISTINCT ON project` for each project's next deadline, one query each for deadlines, funding, ethics, overdue top 20, unassigned, integrations, members and last-active. Counts of "overdue" come from the aggregate, so the "20 shown of N" line is accurate. The flat-count test is the guard against N+1.
- *People / surveillance:* counts and one "last active" time only (D172). Last active is the newest audit event per actor in the lab (index `audit_actor_time_idx`), not a timeline.
- *Unassigned after access change:* there is no flag on a task for this, so the rule joins the audit trail (`task.unassigned` events from `unassign_lost_access`) to tasks that are still open and unassigned. Reassigning a task removes it from the list on its own.
- *Health:* computed on the server so the table, the tile numbers and any future API client agree, and each row carries its reasons for the tooltip.
- *Look:* tiles and cards use only the semantic tokens (`danger`, `warning`, `success`, with their `-text` variants for text on the tinted surface), so light and dark both pass contrast. Colour is paired with an icon and a word everywhere. Tiles link to the card below by anchor. No charts: the numbers are the message, and counts in a sortable table beat a bar per project; no dependency was added. Table is sortable with real buttons and `aria-sort`; default sort is worst health first.
- *Default landing:* the lab index route switches on permission rather than redirecting at login, so members and viewers are untouched and the old "Home" link works for everyone. The existing e2e step that looks for a "Projects" heading still works because the dashboard's table section has that heading.
- *Training:* the training agent's `expiring` endpoint exists, so the card is built and fetched separately; it links to `/labs/<id>/training` (that page belongs to the training agent; until it exists the link lands on the "coming soon" page).

**Issues hit**
- Scoped managers refuse unscoped `update()` in tests; fixture timestamps are back-dated with `.for_lab(lab)`.
- The permission matrix has a completeness test, which fails while another agent's `training:*` routes have no rows. That is theirs to fix; the dashboard rows pass (`-k dashboard`).
- While the training app was half-installed the dev backend failed its system check (`documents.Attachment.training_record`), so the Playwright run had to wait for it.
- Date-only strings are parsed as local dates in `lib/dashboard.ts`, because `new Date("2026-11-20")` is UTC and shows the previous day west of Greenwich.
- `makeLab`-style Vitest fixtures needed the training endpoint mocked with a 404 to prove the card hides on error.

**Known limits**
- "Done in 30 days" is approximate (see D172). Lists beyond 20 are not paged. Project health ignores ethics. Leads shown are explicit project leads only; pi and lab_admin are implicit leads of every project (D19) and are not repeated.

## Training and certification tracking (training agent, 2026-11-05)

Decisions: D175-D179 in `docs/DECISIONS.md`. App: `backend/training/`. Front end: `frontend/src/pages/training/`, `components/training/`, `pages/admin/TrainingSection.tsx`.

**What was built**
- **Requirements** (`TrainingRequirement`): name, category (ethics, safety, biosafety, chemical, data/privacy, equipment, other), validity in months or never, applies to everyone, to roles or to people on chosen projects, optional https link, notes. Read by every member; managed with the new perm `manage_training` (pi, lab_admin).
- **Records** (`TrainingRecord`): member, completed-on, expiry (computed from the validity when blank, editable), notes, verified-by/at, certificate. Renewals are new rows; the latest completion counts.
- **Endpoints** under `/api/labs/<lab>/training/`: `requirements/`, `requirements/<id>/`, `records/`, `records/<id>/`, `records/<id>/verify/`, `records/<id>/certificate/` (GET download, POST upload), `compliance/` (managers), `my/` (caller), `expiring/?days=60` (managers; this is what the PI dashboard card calls).
- **Compliance matrix** in Admin > Training with a Verify button per unverified record, plus the requirement list and form. **My training** (sidebar, every member): required list with status badges, a log-a-completion form with optional certificate, own records.
- **Reminders** (`training/jobs.py`, beat entries in `config/settings.py`): daily expiry reminders at 60/30/7 days and on expiry with the D29 tightest-threshold dedupe; Monday digest of expired and missing items for pi and lab_admin.
- **Onboarding**: an item can link a required training; the checklist ticks it by derivation (D179).
- **Seed**: `seed_pilot` now adds 3 fake requirements, 9 fake records (one expiring in about 25 days, two expired, one missing) and a linked onboarding item. Idempotent (checked by running it twice: 3 requirements and 9 records both times).

**Design choices and why**
- *Certificates*: extended `Attachment` with a third owner rather than a link table. A link table would not remove the need to relax the D38 check (an attachment row has to have an owner), so it would add a table for the same constraint change. The constraint is now "exactly one of three" (migration `documents/0006` drops the old one, `0007` adds the field and the new one). Access is through the record only: the generic attachment routes filter by project, so a certificate 404s there for everyone, a PI included. Test: `test_certificate_rule_and_access`. I moved the audit-and-stream half of the download view into `documents.views.download_response` so the certificate route does not copy it.
- *Privacy*: `TrainingRecord.visible_rows` (the hook ethics already uses) limits non-managers to their own rows, so every route, including nested ones, 404s for another person's record. Verify, compliance and expiring are manager-only (403). Viewers can log their own records (they may need WHMIS too); this is a choice, one line to change.
- *Verification honesty*: changing dates or replacing the certificate clears `verified_at`, so a member cannot edit a signed-off record into something the PI never saw. A verified record can only be deleted by a manager. Records are soft-deleted (D24) because a certificate attachment PROTECTs the row.
- *Status counts unverified records* as done so people are not marked non-compliant while waiting for a PI; the matrix labels them "Not verified".
- *Emailed*: expiry reminders and the digest are in `EMAIL_KINDS` (amends D71). They reuse the generic `notification` email template, so no new templates.
- *No new permission for self-service*: the routes use `view_lab` and the scoping does the rest, avoiding a `log_training` perm that every role would hold anyway.
- *Onboarding by derivation*: writing completion rows would go stale when a certificate lapses, and would need an audit trail for something the system, not a person, decided.

**Issues hit**
- Shared tree: my first `makemigrations` run swept up another agent's `InstitutionSSO` model. I deleted that generated `core/0008_alter_notification_kind_institutionsso.py` and kept only my notification-kind change as `core/0008_training_notification_kinds.py`; the SSO agent's `0009_institutionsso` then built on mine. The generated `audit/0013` contained only my actions.
- `LabScopedQuerySet.update()` refuses to change a `lab_parents` field. Adding `training_requirement` to `OnboardingItem.lab_parents` made a test that nulled it with `update()` fail with `CrossLabError`; the test now deletes the requirement and relies on the composite FK `SET NULL`.
- `drf-spectacular` hashed enum names for the new `status` and `category` fields; fixed with `ENUM_NAME_OVERRIDES` (TrainingCategoryEnum, TrainingAppliesToEnum, ComplianceStatusEnum). Serializer classes carry a `Training` prefix so schema names are unambiguous, except `Expiring` and `ExpiringItem`, which stay unprefixed because the dashboard agent already typed against `Schemas["Expiring"]` (renaming broke `tsc` in their files, so I reverted that one rename).
- `spectacular --validate` currently reports errors from the assistant app (`GrantDetailView` has no serializer); not mine. Types were generated without `--validate`.
- Bash heredocs containing apostrophes broke the shell tool, so large files were written with the editor tool and shell edits were small Python scripts. Repo files are CRLF on disk (git normalises to LF); edits preserved each file's line endings.
- Windows: `docker compose run ... /app/schema.yml` needs `MSYS_NO_PATHCONV=1` under Git Bash or the path is rewritten.
- The permission matrix reported `test_every_endpoint_has_a_matrix_row` failing for `POST core:login-methods`, which belongs to the SSO agent (their row was not there yet); all training rows pass.

**Tests**
- Backend `training/tests/test_training.py`: date and expiry computation, status boundaries (60 days, expiry day), latest-record logic, role and project applicability, expiring endpoint, privacy (a member cannot read, patch, delete, verify or fetch another member's record or certificate), manager access and audit, edit-clears-verification, delete rules, requirement permissions and the 409 guard, cross-lab ids, certificate rules (one owner, route isolation, replacement), reminder thresholds, dedupe, missed-run catch-up, no reminder for never-expires or superseded records, deactivated members, email sent, weekly digest and its dedupe, onboarding derivation.
- Matrix: 16 hand-written rows in `tests/test_permission_matrix.py`, fixtures for both labs; the cross-lab swap covers every training endpoint with an id, and Lab B tags (including the certificate bytes) are scanned for leaks.
- Vitest `pages/training/training.test.tsx`: matrix statuses and summary, Verify only when allowed, My training list, sidebar entry, logging a completion, date validation. `AdminPage.test.tsx` mocks the new calls.

**Known limits**
- A requirement with records cannot be deleted (409); there is no archive state.
- The matrix has one column per requirement and no paging or filters; fine for a lab, not for hundreds of people.
- No bulk import of records and no unverify action (an edit that changes dates clears verification instead).
- Certificates are PDFs or images up to the usual 50 MB attachment cap; there is no inline viewer, the link opens the file.

## SSO agent: institutional sign-in with SAML 2.0 (D152 to D159)

Goal: when University of Alberta IT registers us as a service provider, CCID sign-in works by configuration only. That is now true: one `manage.py configure_sso` run plus two deploy settings (D158). No code change is needed per institution.

### What was built

- **Library:** allauth's own SAML provider (python3-saml under it). Added `django-allauth[mfa,socialaccount,saml]`, and pinned `xmlsec==1.3.18` and `lxml==6.1.3` as wheels only. Licences: python3-saml MIT, xmlsec MIT, lxml BSD-3-Clause, isodate BSD-3-Clause. `scripts/check_licenses.py` passes (68 packages).
- **Config model** `core.InstitutionSSO` (migration `core/0009_institutionsso`, which follows the training agent's `0008`). It has one row per institution: slug, enabled, email domains, IdP entity ID, SSO URL and certificate, optional metadata URL, attribute mapping, and `require_sso`.
- **Editing, superusers only:** `core/admin.py` (the admin only runs under DEBUG, D41; every admin permission checks `is_superuser`, and the page shows the SP URLs to send to IT). For production there is `core/management/commands/configure_sso.py` (a JSON file in, the same validation, prints the SP URLs).
- **allauth wiring (all in `core/auth.py`, still the only module that imports allauth):**
  - `SocialAccountAdapter.list_apps` turns enabled rows into in-memory SAML apps, with provider id `saml:<slug>`.
  - `authenticate_by_email` gained the SAML branch. The IdP vouches only for its own domains, and only verified local addresses link.
  - `pre_social_login` refuses any SAML login whose email is missing or outside the domains.
  - `AccountAdapter.pre_authenticate` and `validate_unique_email` enforce `require_sso`.
  - `login_methods_for_email` and `sso_for_email` do the routing. `sp_urls` lists the SP URLs, and `fetch_idp_metadata` fetches metadata through the safe client.
  - The `auth.login` receiver now records the method.
- **API:** `POST /api/auth/login-methods/` (`core/views.py`, `core/urls.py`). It has a permission-matrix row (2xx for every persona) and a payload entry.
- **Settings:** the SAML app is in `INSTALLED_APPS`. `SECURE_PROXY_SSL_HEADER` is set when `TRUSTED_PROXY_COUNT` is set. There is a `login_methods` throttle (60 a minute).
- **SPA:**
  - `LoginPage` is email-first. An SSO domain gets "Continue with <institution>", plus "Use a password instead" when allowed and "Use a different email". Any other domain gets the password form with the email filled in.
  - The Google button stays on the email step.
  - The callback page now says "Sign-in did not finish", because it serves SSO as well as Google.
  - The e2e login helpers (`e2e/helpers.ts`, `e2e/global-setup.ts`, `e2e/screenshots.spec.ts`) click Continue first.
- **Docs:** D152 to D159, ARCHITECTURE section 7, and a MANUAL_TESTS section with the test-IdP walkthrough and the request for UAlberta IT.

### Design choices and why

- **The model, not settings or allauth `SocialApp` rows.** SSO is per-institution data that a superuser adds when an institution joins, without a deploy. Domains, require-SSO and the institution link need a home that `SocialApp` doesn't have, so the adapter builds the allauth app from our row. That is the same pattern allauth uses for settings-based apps, and it needs no copy kept in sync.
- **Superusers only, no API:** the config decides who may vouch for an email address. A wrong domain would let an IdP sign people into existing accounts. Lab admins only ever pick an institution by name (D146) and cannot reach this.
- **Metadata fetched on save, never at sign-in.** allauth's built-in `metadata_url` mode fetches with plain urllib during login. That gives no SSRF guard, no size cap, and puts a network dependency in every login. Instead, a save fetches through `integrations.http.send` (https, public IPs only, pinned connection, no cross-host redirects, deadline and size cap) and stores the parsed values. Re-saving refreshes them.
- **Signed assertions required** (as the brief asked). Shibboleth's default is to sign the Response only, so the IT request explicitly asks for signed assertions. If they refuse, relaxing it is one line (`want_assertion_signed` in `core.auth._saml_app`); don't do it lightly.
- **Linking an existing password account:** link it, keep the password, and audit `auth.social_connected`. Refusing would strand every existing UAlberta user who signed up with a password. Wiping the password is allauth's defence for unverified matches, and we never link those.
- **Email on every login must be in-domain,** even for a returning user found by uid. This stops an IdP from asserting an address outside its domains at any point.
- **`require_sso` blocks password sign-in and password signup, not password reset or adding the address.** Reset alone gains nothing because the password can't be used. Adding the address as a secondary is how a gmail-based account gets linked to SSO later.
- **POST, not GET, for login-methods,** so addresses don't land in access logs. It answers per domain, so it can't be used to enumerate accounts.
- **SP entity ID pinned to `FRONTEND_URL`,** so the identity UAlberta registers can't change with the Host header.
- **SP metadata validity of ten years:** python3-saml's default is two days, and Shibboleth refuses expired saved metadata. Without this the integration would break silently two days after IT loads our file.

### Issues hit

1. **The xmlsec "system libraries" turned out not to be needed.** xmlsec 1.3.18 ships manylinux wheels (x86_64 and aarch64) with libxml2 2.14.6 statically bundled, the same version lxml 6.1.3 bundles. Both Dockerfiles are therefore unchanged. I pinned both with `--only-binary`, so pip can never fall back to a source build (which would need libxmlsec1-dev, pkg-config and a compiler) or pick an lxml whose libxml2 differs. That mismatch is the classic `lxml & xmlsec libxml2 library version mismatch` import error. `docker compose build backend worker beat` succeeds, and `Dockerfile.prod` installs the same requirements file.
2. **Rebuild order.** Adding the SAML app to `INSTALLED_APPS` before the image had python3-saml would have crashed the shared dev server on autoreload. The images were rebuilt and the backend and worker recreated first, then settings were changed.
3. **`KeyError: HTTP_HOST`:** allauth's SAML code reads `request.META["HTTP_HOST"]`, which Django's test client doesn't send. The tests pass a Host. Real browsers always send one.
4. **`sp_acs_url_invalid` in tests:** python3-saml rejects single-label hosts such as `testserver`. `localhost` is special-cased, so the tests use it. Dev (`localhost:5173`) and real domains are fine.
5. **Behind Caddy, Django thought requests were http:** there was no `SECURE_PROXY_SSL_HEADER`. The SP metadata would have advertised an http ACS and the Destination check would have failed. Fixed in settings (D155), active only when `TRUSTED_PROXY_COUNT` is set.
6. **The production CSP blocks the IdP redirect:** `form-action 'self' https://accounts.google.com` would stop the browser following our form POST's redirect to the IdP. I didn't change the Caddyfile, because the IdP host isn't known yet. It is a documented deploy step (D158, MANUAL_TESTS).
7. **Password wiped in one test:** linking an account whose `EmailAddress` was stored as `Ada@...` wiped its password. allauth's `wipe_password` matches lower-case exactly. allauth always stores lower-case, so only hand-made rows are affected, and Google has the same behaviour. Recorded in D159 and not worked around.
8. **IdP-initiated test was first rejected by schema** (an empty `InResponseTo`), not by the IdP-initiated rule. The test now omits the attribute, and the log confirms "IdP initiated SSO rejected". I also ran each negative test with logging to check that each fails for its own reason: "not signed", "Signature validation failed", "not a valid audience", "expired", PermissionDenied for replay, and our domain refusal.
9. **Shared-tree noise, not mine:**
   - The permission matrix currently fails for every row because the MCP agent's `/mcp` and `/api/oauth/register/` routes are not DRF views and not yet exempt.
   - `spectacular --validate` currently fails on the data-management agent's half-written `provenance/urls.py` (`dmp` undefined).
   - I checked my matrix rows with a temporary copy of the matrix that exempted their prefixes, then deleted it. `core:login-methods` and `test_every_endpoint_has_a_matrix_row` passed.
   - The committed `schema.yml` and `api-schema.d.ts` already include `/api/auth/login-methods/` (another agent's regeneration). I checked that the generated types match the schema.
   - Also, `make types` under Git Bash needs `MSYS_NO_PATHCONV=1`, or `/schema/schema.yml` is rewritten into a Windows path.

### What a human must do with University of Alberta IT

1. **Fix the production origin first.** `FRONTEND_URL` must be its final https value, because the SP entity ID is derived from it and changing it later means re-registering.
2. **Send IT the request in `docs/MANUAL_TESTS.md`** ("Institutional SSO: request to UAlberta IT"). It covers the metadata URL, entity ID, ACS, attributes, NameID and signing. Expect a service request to IST for a Shibboleth SP registration. They may ask for a short privacy or data-use description (we store name, email and ePPN only).
3. **When they reply,** you'll get their IdP metadata URL (or an entity ID, SSO URL and signing certificate). Write the JSON and run `python manage.py configure_sso ualberta.json` in the backend container. Start with `"enabled": false` to check the output, then rerun with `true`.
4. **Add their SSO host to the CSP `form-action`** in `deploy/Caddyfile`, and confirm `TRUSTED_PROXY_COUNT=1`.
5. **Test with a real CCID** (MANUAL_TESTS steps). Then decide on `require_sso`. Leave it off until people with existing password accounts have signed in with SSO once; it does not change their accounts.
6. **Certificate rollover:** when IT announces a new IdP signing key, rerun `configure_sso` at the switch time (D159).

### How to test

- **Automated:** `docker compose run --rm --no-deps -e TEST_DB_NAME=test_s5 backend pytest core/tests/test_saml_auth.py core/tests/test_auth.py core/tests/test_google_auth.py`, which gives 54 passed. `test_saml_auth.py` has 24 tests:
  - routing and the endpoint
  - the headless provider list
  - a new user, linking a verified primary address, and linking a verified secondary address
  - an unverified local address never links
  - outside-domain, look-alike-domain and missing emails are refused
  - unsigned, tampered, wrong-key, wrong-key-with-right-cert, wrong-audience and expired responses are refused
  - replay, in another browser and in the same one
  - IdP-initiated logins are refused
  - require-SSO
  - SP metadata, including validity
  - metadata fetch through the safe client, and config validation
  - the admin is superuser-only
  - the management command

  Responses are signed with a key pair generated in the test (python3-saml `add_sign`) and validated by python3-saml for real; no IdP is mocked.
- **Vitest:** `src/pages/sso.test.tsx` (3 tests: the SSO button and its form fields, require-SSO with no password option, and the fallback to password), plus the updated login tests in `pages.test.tsx` and `google.test.tsx` (23 passed across the three files).
- **Manual:** with a local SimpleSAMLphp IdP, see MANUAL_TESTS "Institutional SSO (SAML)".


## MCP server and AI tool layer (MCP agent, D160-D169, 2026-11-05)

Goal: people bring their own AI. Consumer subscriptions (Claude Pro/Max, ChatGPT Plus/Pro) cannot be called by our app, so the app is a **remote MCP server** that people add to their own Claude or ChatGPT as a custom connector; their subscription pays for the model and our server only answers permission-checked tool calls. The tool layer is shared with the later in-app bring-your-own-key assistant.

### What was built

- **New app `backend/assistant/`** (no new dependency):
  - `tools.py`: the tool layer (D160). `definitions()` and `call(ctx, name, args)`; `Context(user, lab_ids, can_write, via, client, grant_id, request)`. 11 read tools (`list_labs`, `list_projects`, `project_overview`, `search`, `list_tasks`, `get_task`, `get_document`, `lineage_trace`, `list_ethics_approvals`, `list_funding`, `my_notifications`) and 3 write tools (`create_task`, `add_task_update`, `create_decision_draft`). Each has a title, a description written for a model, and a JSON Schema with `additionalProperties: false`; arguments are validated before anything runs.
  - `mcp.py`: `POST /mcp`, the Streamable HTTP transport (D161, D166).
  - `oauth.py`: protected resource metadata, authorization server metadata, dynamic client registration, token endpoint (D161, D165).
  - `services.py`: grants, hashed tokens, the code flow, refresh rotation and replay detection, CIMD fetching, redirect URI policy, rate limiting (D162-D165).
  - `views.py` and `serializers.py`: the consent API and the grant lists for Settings and for lab managers (D164, D168).
  - `models.py` and `migrations/0001_initial.py`: `OAuthClient`, `AIGrant`, `AIToken`. `audit/migrations/0014_ai_access_actions.py` adds `ai_access.granted`, `ai_access.revoked`, `ai_tool.write`.
- **Settings**: `MCP_BASE_URL` (default `FRONTEND_URL`), `MCP_OAUTH_REDIRECT_HOSTS`, `MCP_CIMD_HOSTS`, `MCP_ALLOWED_ORIGINS`, throttle `ai_token`, enum names `AiGrantKindEnum` and `AiAccessEnum`. `config/urls.py` mounts `assistant.urls` at the root.
- **Proxies**: Vite proxies `/mcp` and `/.well-known` (dev), Caddy's `@backend` matcher adds `/mcp /.well-known/*` (production).
- **Frontend**: Settings gets "Connected AI apps" (shows the MCP URL to paste, lists apps with labs, access and last use, Revoke), "Access tokens" (list, Revoke, a create form with name, labs, access and expiry; the token is shown once with a Copy button and the ready-made `claude mcp add` command) and, for pi and lab_admin, "AI access to <lab>" with Remove access (`pages/settings/AiAccessSections.tsx`, `hooks/ai.ts`). The consent page is `/oauth/authorize` (`pages/OAuthConsentPage.tsx`).
- **Tests**: `assistant/tests/test_tools.py` (28: scoping per tool and persona, restricted ethics, funding amounts, lineage, viewer and read-only writes, audit), `test_mcp.py` (25: legacy and modern protocol through the real endpoint with a PAT and with an OAuth token, header validation, Origin, 401 challenge, step-up 403, deactivation, removal and revocation, rate limit, metadata, DCR, CIMD, PKCE, code reuse, refresh rotation and replay, consent API, PAT and lab-manager APIs), `test_token_leaks.py` (1, 14 real tokens through every surface). Permission matrix rows for the 6 new SPA endpoints plus fixtures in both labs and a Lab B leak name. Vitest `pages/AiAccess.test.tsx` (8). Types regenerated with the two `types:` commands.

### How a call is checked (security model)

1. **Transport**: only POST; `Origin`, when present, must be our own origin or listed in `MCP_ALLOWED_ORIGINS`, else 403 (DNS rebinding). Django's `ALLOWED_HOSTS` pins `Host`. Session cookies are never accepted on `/mcp`, so the endpoint is `csrf_exempt` safely; there is no CORS on `/mcp` or the token endpoint.
2. **Token**: `Authorization: Bearer` only (never a query string). We hash it and look up an access token or PAT; it must be unexpired, its grant unrevoked and unexpired, its user active, and an access token must have been issued for this MCP URL (RFC 8707 audience). Otherwise 401 with `WWW-Authenticate: Bearer resource_metadata="<base>/.well-known/oauth-protected-resource/mcp", scope="mcp:read"`.
3. **Rate**: 120 requests a minute per grant, 30 writes a minute per grant (429, `Retry-After: 60`).
4. **Labs**: the grant's labs, intersected with the user's current memberships, on every call (D163).
5. **Scope**: a write tool with a read-only OAuth grant is HTTP 403 `insufficient_scope` (Claude re-asks consent); with a read-only PAT it is a tool error.
6. **Tool**: arguments are schema-checked; roles are re-read (`forget()`); objects come from `scope()` and each returned object passes `can()`; a write passes `can(EDIT_CONTENT)` and then the normal service (its own validation, the assignee rule, the decision rules), inside one transaction with the `ai_tool.write` audit event. An unknown id and an id the user cannot see return the same message.
7. **Output**: compact JSON, lists of 25 with a cursor, text cut (descriptions 1,500 to 4,000 characters, posts 2,000, documents 20,000 per call), the whole result refused above 100,000 characters. No tokens, hashes or keys anywhere; no recruitment entries (participant counts and notes); grant amounts only for project leads (D133); approval-linked project names only where visible.

What an AI app can never do: see more than its user sees in the app, see a lab the user did not tick, act after the user is deactivated or removed, delete or change existing records (the three writes only add: a task, a thread post, a draft decision), or reach anything outside these 14 tools.

### Design choices and why

- **Hand-rolled transport instead of the `mcp` SDK** (D161). The SDK (MIT, v2.3.0, depends on starlette, uvicorn, anyio, pydantic, sse-starlette, httpx2, pyjwt and more) is async; mounting it beside Django means either a second ASGI service in compose with its own auth and DB access, or converting the WSGI deployment, plus `sync_to_async` around every ORM call. We need five methods, no streaming and no server-to-client requests, so about 300 lines of plain Django are smaller, use our existing permission and audit stack directly, and need no licence review or image rebuild. The tool layer does not depend on the transport, so the SDK can replace `mcp.py` later.
- **Dual-era protocol support** (D161). The current spec (2026-07-28) removed the `initialize` handshake and sessions and puts the version, client info and capabilities in each request's `_meta`, mirrored into `MCP-Protocol-Version`, `Mcp-Method` and `Mcp-Name` headers. Clients in the field (and the Claude and OpenAI docs, which still link the 2025-11-25 spec) may still speak the legacy revisions, so the server answers both: modern requests are validated as the spec says (400 with -32020 header mismatch, -32022 unsupported version, -32602 missing `_meta`, 404 with -32601 for unknown methods) and get `resultType: "complete"`; legacy clients get `initialize` with version negotiation (2025-11-25, 2025-06-18, 2025-03-26) and no session id. Stateless is allowed in both eras.
- **Our own authorization server**, issuer = the site origin, so `authorization_servers` is one entry (Claude uses only the first). The authorization endpoint is a SPA page because sign-in, MFA, Google and SSO all live in the SPA; the server re-validates everything on approve.
- **Both CIMD and DCR** (D165). The spec now prefers Client ID Metadata Documents and calls DCR deprecated; Claude's connector dialog defaults to "Use Claude's published identity" (CIMD) and falls back to DCR; ChatGPT prefers CIMD and supports DCR. CIMD means fetching a URL the client names, so it goes through the existing SSRF-pinned integrations client and only to `MCP_CIMD_HOSTS`. DCR is open to anyone, so the defence is the redirect URI allowlist: codes can only be delivered to claude.ai, claude.com, chatgpt.com or a loopback address.
- **Read by default, write by step-up** (D167). The first sign-in asks only for `mcp:read`; the consent page preselects what the app asked for and the person can always pick less. Write tools return the spec's `insufficient_scope` challenge, which Claude turns into a second consent.
- **Hashes, not MultiFernet, for tokens** (D162). We never need a token's plaintext after issuing it, so a one-way hash is safer than reversible encryption and needs no key rotation. Prefixes (`rwa_`, `rwr_`, `rwp_`) make leaked tokens recognisable to secret scanners.
- **One grant, many labs**. A person picks labs on one consent screen; lab managers remove only their own lab from a grant, and the grant ends when no lab is left. Audit events are written once per lab so each lab's log is complete.
- **Audit**: grants and revocations always; every write tool call (with `via: "mcp"`, the client's registered name and, for context, its self-reported `clientInfo` name); reads not audited, like browsing, except document reads, which the app already audits.
- **Decision drafts**: decisions have no draft state and adding one would change the Workflow UI, so a draft is a normal decision titled "Draft: ..." that people edit or delete in the app.
- **ChatGPT's OIDC scopes**: we do not advertise `openid`, `email` or `profile`, so ChatGPT should not request them; if it does, the request fails with `invalid_scope` (unverified, see below).

### Issues hit

1. The MCP spec moved to 2026-07-28 since the earlier plan was written: no `initialize`, no sessions, per-request `_meta` and mandatory mirrored headers. Built dual-era support instead of the plain 2025-06-18 server the plan assumed.
2. `@tool(name, title, description, **params)` collided with tools that have `title` and `description` parameters; the decorator now takes them positional-only.
3. Postgres refuses `SELECT ... FOR UPDATE` across a nullable outer join (`select_related("grant__client")`); the lock is `of=("self",)`.
4. Replay detection first revoked the grant inside the same atomic block that then raised `invalid_grant`, so the revocation rolled back. `_spend` now commits the "used" mark first and revokes outside the failed transaction.
5. My first rate-limit JSON-RPC code (-32099) was inside the range the spec reserves for itself; it is -31000 now.
6. Git Bash rewrote `/app/schema.yml` to a Windows path in `docker compose run`; the type commands need `MSYS_NO_PATHCONV=1` from Git Bash (cmd or PowerShell are unaffected).
7. drf-spectacular could not describe the two DELETE views without a `serializer_class`, and `GrantKind` collided with other `kind` enums; fixed with `serializer_class` and `ENUM_NAME_OVERRIDES`.
8. Another agent's half-finished `provenance/urls.py` (data management plans) broke URL loading for a while; I waited rather than touching it. `core/tests/test_tenancy_lint.py` still fails on their `provenance/tests/test_dmp.py`, and two `E501` lines in the matrix (`core:login-methods`, `labs:dashboard`) are other agents' rows.
9. The running Vite dev server did not reload its proxy table after `vite.config.ts` changed (Windows bind mount), so `http://localhost:5173/mcp` returns 404 until `docker compose restart frontend`. `http://localhost:8000/mcp` works directly.
10. OpenAI's help centre refuses WebFetch (403); it was read through another fetcher.
11. Smoke test on the dev stack: I created a 1-day read-only PAT named "smoke test (delete me)" for `admin@example.test`, ran `initialize`, `tools/list` and every read tool against the seeded lab, confirmed a write is refused, and revoked it. Its `ai_access.granted` and `ai_access.revoked` events remain in the dev audit log.

### Verified against official docs (2026-11-05) and not verified

Verified by reading the source:
- MCP specification 2026-07-28 (modelcontextprotocol.io): statelessness and per-request `_meta`; versioning and the legacy/modern compatibility rules; Streamable HTTP (single POST endpoint, `Origin` 403, 202 for notifications, header mirroring and validation, GET/DELETE 405 for legacy traffic, no sessions); `server/discover`; tools (annotations untrusted, `structuredContent` plus a text copy, tool errors as `isError`); authorization (RFC 9728 PRM with `authorization_servers`, well-known path order, RFC 8414, CIMD preferred and DCR deprecated, PKCE, RFC 8707 resource, 401 vs 403 `insufficient_scope`, `iss` in authorization responses, refresh rotation for public clients).
- Claude connector docs (claude.com/docs/connectors/building/authentication and lazy-authentication; support.claude.com "Get started with custom connectors"): 401 with `resource_metadata` required; Claude uses the first authorization server; CIMD chosen only when `client_id_metadata_document_supported` is true and `none` is a token auth method, else DCR; callback `https://claude.ai/api/mcp/auth_callback` (and possibly `claude.com` later); Claude Code uses loopback redirects on any port for `localhost` and `127.0.0.1`; PKCE S256 always; scope from the 401 challenge; `offline_access` appended when listed; form-encoded token requests; `invalid_grant` on refresh failure; 10 s and 30 s time limits; traffic from 160.79.104.0/21; custom connectors on Free (one), Pro, Max, Ultra, Team and Enterprise; menu paths below.
- Claude Code docs (code.claude.com/docs/en/mcp): `claude mcp add --transport http <name> <url> --header "Authorization: Bearer <token>"`, and `/mcp` or `claude mcp login <name>` for OAuth.
- OpenAI Apps SDK auth docs (developers.openai.com): PRM and AS metadata fields, `code_challenge_methods_supported` required, CIMD preferred (`https://chatgpt.com/oauth/client.json` or `.../oauth/{callback_id}/client.json`), DCR supported, redirect URIs `https://chatgpt.com/connector_platform_oauth_redirect` or `https://chatgpt.com/connector/oauth/{callback_id}`, `resource` sent on both requests.
- OpenAI help centre, "Connecting custom MCP servers in ChatGPT" (updated late October 2026): full MCP for Business and Enterprise/Edu on the web; admins add servers under Plugins > + > Add custom MCP server without Developer Mode; refresh tokens via `offline_access` in metadata.
- `mcp` on PyPI: MIT licence, version 2.3.0, its dependency list.

Not verified (no account, no public URL):
- An end-to-end connection from claude.ai or ChatGPT. The behaviour is tested against the documented requests, not the real clients.
- Where Claude's hosted CIMD document for claude.ai lives (only Claude Code's, `https://claude.ai/oauth/claude-code-client-metadata`, is named in the docs). If it is not on an allowed host the consent page says "Apps from that host are not allowed here"; choose "Register automatically" in Claude or add the host to `MCP_CIMD_HOSTS`.
- Whether ChatGPT asks for OIDC scopes we do not advertise, and whether its plugin flow needs the Apps SDK per-tool `securitySchemes` (we require sign-in for every request, which its docs show as supported).
- ChatGPT on Plus and Pro: the help article's FAQ, as quoted by search results, mentions Pro read/fetch only; not confirmed on the page I could read.

### Connect it to Claude (claude.ai, Desktop, mobile)

Prerequisite: the app must be reachable at a public **https** address, because Claude connects from Anthropic's cloud, not from your computer. Use the production deployment (`docs/DEPLOY.md`; Caddy already routes `/mcp` and `/.well-known/*`), or a tunnel you set up yourself to the dev stack (for example Cloudflare Tunnel or ngrok to `http://localhost:5173`). For a tunnel, set `FRONTEND_URL=https://<tunnel host>` (or `MCP_BASE_URL`), add the host to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, let Vite accept the host (`__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=<host>` in the frontend's environment; unverified for this Vite version), and restart. If you firewall the server, allow `160.79.104.0/21`.

1. Pro or Max: in Claude open **Customize > Connectors**, click **+ Add**, then **Add custom connector**. Team or Enterprise: an Owner opens **Organization settings > Connectors > Add > Custom > Web** first; members then find it under **Customize > Connectors** and click **Connect**.
2. Name it (for example "Research Workspace") and enter `https://<your host>/mcp`. Click **Continue**.
3. Authentication: **Sign in now**. OAuth client: **Use Claude's published identity (Recommended)**, or **Register automatically** if that fails (see "Not verified"). Leave Request headers empty. Click **Add**, then **Connect**.
4. A window opens on `https://<your host>/oauth/authorize`. Sign in as usual (with your authenticator code if MFA is on), tick the labs Claude may read, choose **Read only** or **Read and write** (only offered when Claude asked for it), and click **Allow**. The window returns to Claude.
5. In a chat, enable it from **+ > Connectors**. Try "List my labs" or "What's overdue in <project>?".
6. If you chose Read only and ask Claude to create a task, Claude asks you to reconnect; approve **Read and write** to allow it.
7. To disconnect: **Settings > Connected AI apps > Revoke** in our app (takes effect immediately), and remove the connector in Claude. A PI or lab admin can remove a member's access to their lab under **Settings > AI access to <lab>**.

### Connect it to Claude Code (works on localhost)

1. Once, after this change: `docker compose restart frontend` so Vite proxies `/mcp`.
2. In the app: **Settings > Access tokens**, name the token, tick labs, pick access and expiry, **Create token**, copy it (it is shown once).
3. Run the command the page shows, for example `claude mcp add --transport http research-workspace http://localhost:5173/mcp --header "Authorization: Bearer rwp_..."` (`http://localhost:8000/mcp` also works).
4. `claude mcp list` should show it connected; then ask Claude Code about your labs.
5. OAuth instead of a token: add it without `--header`, then run `/mcp` (or `claude mcp login research-workspace`) and approve in the browser; loopback redirects are allowed.

### Connect it to ChatGPT (Business, Enterprise or Edu)

1. The app must be at a public https URL (as above).
2. A workspace admin or owner (or, on Enterprise/Edu, a member given the "Create plugins with MCPs" permission) opens **Plugins**, clicks **+**, then **Add custom MCP server**.
3. Enter a name and `https://<your host>/mcp`, choose OAuth for authentication, tick the risk acknowledgement, and click **Create as a plugin**. ChatGPT finds the metadata, registers itself (CIMD or DCR) and opens our consent page: sign in, pick labs and access, **Allow**. It then lists the tools.
4. Test in a chat by typing `@` and choosing the plugin; ChatGPT asks for confirmation before write actions. Admins publish it for the workspace from the Admin console.
5. Older "Apps" settings (Workspace settings > Apps > Create) work the same way. Plus and Pro: not confirmed (see above).

### Known limits

- No resources, prompts, SSE streaming or `subscriptions/listen`; tools only (`listChanged: false`).
- DCR clients are never deleted. ponytail: they accumulate one row per fresh Claude connection; add a daily prune of clients with no grant older than a week if the table grows.
- No RFC 7009 revocation endpoint; people revoke in Settings. No per-tool allowlist per grant (read or read and write only).
- Rate limits are fixed windows in the shared cache.
- `get_document` returns the document's stored plain text (`search_text`), so headings, tables and formatting are flattened.


## Data management plans, Borealis and FRDR (D180-D186)

### What was built

- **DMP** (`backend/provenance/dmp.py`, models appended to `provenance/models.py`, migration `provenance/0003_data_management_plan` with composite lab FKs through `core/lab_db.py`, audit migration `audit/0015`). Routes `data-management-plan/`, `.../approve/`, `.../revisions/` under a project. Eight template sections, status, last reviewed, external link, one attachment, a revision after every save. Matrix rows added by hand (`provenance:dmp`, `dmp-approve`, `dmp-revisions`) and a plan added to the matrix world so approve has something to approve.
- **Frontend**: `DmpPanel.tsx` above the datasets on Workflow > Data (view with collapsible sections, edit form, status and last reviewed, attachment picker, approve, two-step delete, history list, institution links in the `data_management` category), `hooks/dmp.ts`, types in `lib/api-types.ts`. Only semantic colour tokens are used, so light and dark follow the theme; the "approved, saving reopens it" note uses the warning token. Vitest: `DmpPanel.test.tsx` (8 tests).
- **Dashboard**: `attention.dmp` and `summary.projects_without_dmp` in `labs/dashboard.py`, a card on `DashboardPage.tsx`, a backend test, and the two fixture fields added to `DashboardPage.test.tsx`.
- **Providers**: `integrations/providers/borealis.py` and `frdr.py`, both in `registry.ENABLED`, tests `test_borealis.py` and `test_frdr.py` (each a `ProviderContract` subclass plus specific tests).

### Design choices and why

- **Revisions table instead of the document revision pattern.** A document revision holds block JSON and supports restore; a plan is eight strings. A numbered snapshot per save is a dozen lines and the history shows who changed what and when. No restore (D186).
- **Approve is its own endpoint, and edits reopen an approved plan.** Otherwise a contributor could change an approved plan without anyone noticing. The cost is that a lead has to approve again after a typo fix.
- **Leads approve and delete, contributors write.** Same split as funding amounts (D133). Delete is lead-only because it removes the history too.
- **Borealis uses the versions route, not the plain dataset route.** Verified in the Dataverse guide (current version) that `/api/datasets/:persistentId/versions/:latest-published?persistentId=...` exists and that `excludeFiles` is a documented parameter of the version routes (it defaults to true in current releases, older ones defaulted to false, so it is sent explicitly). The plain route always returns the file list.
- **FRDR through DataCite.** FRDR's search API is Globus Search and needs a login; DataCite is public, stable, and returns the FRDR page address. The framework treats `api.datacite.org` as the only API host.
- **No `..` in DOIs.** A first draft allowed `.` anywhere in a segment and a test caught `10.5683/SP4/../../x` parsing. Segments now start with a letter or digit.
- **Contract allowlist.** `CONTENT_PATHS` was extended for Dataverse; a first attempt that also banned `/files` broke Drive, Dropbox and Box (their metadata endpoints are `/files/<id>`), so it was removed.

### Issues hit

- Heredocs containing apostrophes failed in the shell tool here; new files were written with the file tool instead.
- Files in this repo mix LF and CRLF (`audit/models.py`, `provenance/models.py`, the matrix test are CRLF; `provenance/urls.py`, `labs/dashboard.py` are LF); edits kept each file's own endings.
- `audit/0015` is a plain `AlterField` of the action choices. It includes whatever other agents had already added to `AuditAction` when it ran, and depends on `0014`. If another agent generates an audit migration at the same time, run `makemigrations --merge audit`.
- **Borealis was in scheduled maintenance for the whole session** (its API and site returned a maintenance page, and the dataset page returned 500). The Dataverse reply shape is therefore taken from the Dataverse guide, not from a live Borealis answer.

### Verified and not verified

Verified live:
- DataCite: `GET /dois/10.20383%2F101.011`, `/dois/10.20383%2F103.01818` and `/dois/10.5683%2FSP4%2FUBVBL1` return the fields the providers read; a missing DOI is 404; the `url:"..." OR url:"..."` search finds an FRDR record by page address; prefix queries show 10.5683 records are Borealis (`https://borealisdata.ca/citation?persistentId=doi:...`) and 10.20383 records are FRDR.
- `https://www.frdr-dfdr.ca/repo/dataset/39e86b8b-57ef-d798-ad3e-9d15273bcc65` answers 200 and `https://doi.org/10.20383/101.011` redirects.
- The Dataverse guide documents the route, `:latest-published`, `excludeFiles` and the version object fields used (`versionNumber`, `versionMinorNumber`, `versionState`, `lastUpdateTime`, `releaseTime`, `datasetPersistentId`).

Not verified:
- A real Borealis API reply (maintenance). The `metadataBlocks.citation.fields[typeName=title]` layout is the standard Dataverse one but unconfirmed here; the first manual test below will confirm it. Whether Borealis treats the DOI case-insensitively in `persistentId` is also unconfirmed (the id is sent as pasted).
- Whether any FRDR record uses the older `https://www.frdr-dfdr.ca/repo/handle/doi:...` page address (10.20383/101.018 does); such a page address is not accepted, the DOI form is.
- Dark and light visual check of the panel in a browser (only the theme tokens were relied on; no screenshot was taken).

### Tests run (`TEST_DB_NAME=test_d5`, scoped)

- `integrations/tests/test_borealis.py`, `test_frdr.py`, `test_registry.py`; `provenance/tests/test_dmp.py`; `labs/tests/test_dashboard.py`; `tests/test_permission_matrix.py`; `tests/test_lab_db_constraints.py`: all pass.
- Vitest: `pages/project/workflow` (Workflow and DmpPanel) and `DashboardPage`: 38 pass. `npm run typecheck` clean. ESLint: no errors.
- Dev database migrated; `schema.yml` and `api-schema.d.ts` regenerated with the Makefile commands.


## In-app assistant, bring your own key (sonnet agent, D187-D192, 2026-11-05)

Goal: people who do not want to (or cannot) connect an external AI app can still use an assistant inside the workspace, paying the AI provider directly with their own key. It reuses the permission-scoped tool layer from the MCP work (`assistant/tools.py`), so the assistant can never see or do more than the signed-in person can in the app.

### What was built

- **Keys (Settings > AI, "Assistant API keys").** One Anthropic and one OpenAI key per person (not per lab). Saving checks the shape, makes one free provider call, then stores the key encrypted with the same MultiFernet as integration tokens (D63). The page only ever shows "Saved: ending 1234". Replace and Remove work; Anthropic has a checkbox for the refusal fallback (D189). `manage.py rotate_integration_keys` now re-encrypts these keys too.
- **Lab policy ("Allow AI assistants").** `Lab.ai_policy` = off, MCP only, or MCP + in-app (default). pi and lab_admin change it under Settings > AI ("AI assistants in <lab>"), with a notice about sensitive data. Enforced on the in-app assistant (403) and on the MCP endpoint (403 when every granted lab is off; an off lab disappears from a connection that names other labs). The MCP server had no such check; it was added in `services.granted_lab_ids` and `policy_blocked` with tests in `assistant/tests/test_policy.py`.
- **Assistant panel.** A side drawer opened from an "Assistant" button in the header on every lab page (`components/assistant/AssistantDrawer.tsx`). It is scoped to the current lab, and to the current project when the page is a project page (a new chat starts when that changes; older chats stay in a dropdown). It shows the privacy notice, a provider and model picker for a new chat, the conversation, tool rows ("List projects: done"), the model that answered, and tokens in and out with a rough dollar figure per answer. Answers stream in. Stop, Try again (for retryable errors) and Delete chat are there.
- **Approve before write.** The three write tools (create a task, add a task update, create a draft decision) stop the stream and open a dialog with the tool name and exact arguments; only the Approve button runs them. Decline, or simply typing something else, declines. The audit event is `ai_tool.write` with `via: "in_app"`.
- **Two adapters.** `assistant/ai/claude.py` (Anthropic SDK, Messages API) and `assistant/ai/openai_responses.py` (OpenAI SDK, Responses API) share only a neutral "finished turn" type (`ai/types.py`); `ai/chat.py` is the provider-neutral loop.
- **Endpoints** (all in the permission matrix with hand-written rows and fixtures in both labs): `GET /api/ai/keys/`, `PUT, PATCH, DELETE /api/ai/keys/<provider>/`, `GET, PATCH L/ai-policy/`, `GET L/assistant/config/`, `GET, POST L/assistant/conversations/`, `GET, DELETE L/assistant/conversations/<id>/`, `POST .../messages/` and `POST .../approvals/` (both streaming).
- **Migrations:** `labs.0005_lab_ai_policy`, `assistant.0002_in_app_assistant`, `audit.0016_ai_key_actions` (two new actions, `ai_key.saved` and `ai_key.removed`). Dev database migrated.

### Design choices and why

- **Manual loop, not the SDK tool runner.** The loop must pause for a person, persist every content block, and stream over SSE. The runner is beta and would have needed workarounds for all three.
- **Messages are stored as the provider sent them** and replayed unchanged (thinking blocks and signatures included). Edited history is rejected by the API for models that keep thinking, so nothing is rewritten; the only exception is Anthropic's own documented rule for a turn that fell back mid-output. A refused or cut-off turn is kept and shown but never replayed (it may be empty or hold a half-written tool call).
- **The system prompt and model are frozen per conversation.** A thinking block's signature covers the system prompt and tool set, so changing either mid-chat would make the API reject the history. The date and lab and project names are baked in when the chat starts.
- **State lives only in the message log.** "Waiting for approval" is an assistant turn with tool calls and no results. This means a reload, a second tab or a crash cannot leave a stuck state, and typing instead of clicking just declines.
- **Only the owner sees a conversation.** Another member, a lab admin and the PI all get 404. Conversations are not lab-scoped models in the D18 sense (like `AIGrant`), so there are no composite lab keys; every query filters on user and lab, and the matrix and cross-lab swap tests prove it.
- **Project scope is a default, not a wall.** The person may already see the whole lab; the lab is the hard boundary (the tool context names exactly one lab).
- **Effort `medium`.** Anthropic recommends it for multistep tool use (`low` is for plain chat). It is sent explicitly so a changed default cannot change cost.
- **Fallback is a per-person setting**, default on, because a fallback answers on a different model and the person may care which one (and what it costs).
- **OpenAI uses the Responses API** because OpenAI's docs say GPT-6 models need it for tool calling. Default `gpt-6.1-sol` (near the flagship at $2/$10 per million tokens).
- **No prompt for caching tricks beyond one top-level `cache_control`.** The system prompt and tools are identical on every step of a chat, so steps 2 to 8 of a tool loop read them from the cache.
- **Anthropic SDK 1.17, not 2.x.** 2.x sends API version `2026-10-21`; the references available described 1.x. Moving to 2.x later is a one-line pin and a read of its migration guide.

### Costs

The lab pays nothing: usage is billed to each person's own key. List prices used for the on-screen estimate (USD per million tokens, in/out): Opus 5.5 4/20, Sonnet 5.5 2/10, Haiku 5.5 0.10/0.50; GPT-6.1 Sol 2/10, GPT-6 Astra 10/50, GPT-6.1 Terra 1/5, GPT-6 Luna 0.10/0.50. A tool-using answer is several model calls (up to 8 per message), each re-reading the conversation, so a question that reads a long document costs more than a short chat; the per-answer token line is there so people see this. Cached input is billed at a tenth. Saving a key costs nothing (it lists models). The server cost is a held web worker per open answer (see "Streaming and deployment").

### Privacy

- Content from records the person can see is sent to the provider they chose, under their own key and account terms. The panel and Settings both say so and warn not to paste participant identifiers; the system prompt tells the model not to ask for or copy identifiers.
- Labs that hold sensitive participant data can turn assistants off (D188). That is the control; nothing else filters record content before it is sent, and we do not redact. The recruitment notes the tool layer already refuses to read stay unreadable.
- Conversations (including what the tools returned) are stored in our database, visible only to the owner, and deleted with the chat. The OpenAI adapter sends `store=false`, so OpenAI is asked not to keep the response; Anthropic's retention follows the person's own account settings.
- Keys: encrypted, never returned, never in a log, audit event, error, admin page, or the DEBUG 500 page (`test_ai_key_leaks.py` pushes two canary keys through every surface, including crashes with the key in memory).
- Prompt injection: record text is untrusted. The system prompt says so, and the real defence is structural: reads are scoped by the person's permissions, and every write needs the person's click on the exact arguments.

### Streaming and deployment

- Dev: Django's server streams; the Vite proxy passes chunks through. I checked this end to end with the real Anthropic SDK against a local stand-in server (see "Issues"): text chunks reached the client 0.6 s apart through `localhost:5174` (a throwaway second stack), not in one lump at the end.
- Production (`deploy/`): gunicorn now runs `--worker-class gthread --threads 8 --timeout 330` (a sync worker serves one request at a time and the arbiter kills it after 30 s of silence, so a minutes-long answer would take down a worker). Caddy gets a dedicated `handle` for the two stream URLs with `flush_interval -1` and a 330 s read timeout. **Not tested on a live Caddy.** If chunks arrive late behind Caddy, exclude `text/event-stream` from `encode`.
- Each open answer holds one gunicorn thread: 3 workers x 8 threads = 24 simultaneous answers. A person can have 3 open and a chat 1 (cache locks that are released when the connection closes or the stream ends).
- Closing the drawer aborts the browser request; the server notices on its next write and stops (the user message stays saved, the unfinished answer does not).

### Issues hit

1. **Keys in the debug page.** The first leak test failed: the serializer (`KeySaveSerializer(data={'api_key': ...})`) is a local variable in the PUT view, and its repr shows the data. Fixed with `@sensitive_variables()` on the view. A second failure showed that `@sensitive_variables("raw", "api_key")` does not hide the decorator's own wrapper arguments (`func_args`) when the key is passed positionally; the bare form (hide everything) is used on every non-generator function that sees a key. On a generator function the decorator does nothing for later frames, but a generator's frames are never in a 500 page here, because `_generate` catches everything.
2. **Matrix vs streaming.** The matrix calls each endpoint as each persona and needs 200s. A first design that locked and wrote in the view returned 409 on the second call. Fix: the lock and the user message are taken when the first chunk is pulled, so an unread response changes nothing. For the same reason "message while an approval is pending" no longer returns 409 but declines the waiting writes (also nicer for people), so one fixture conversation serves both the message and the approval rows.
3. **`DecisionInputSerializer` name clash** with provenance in the OpenAPI schema (merged into one component); mine is `ApprovalDecisionSerializer`. Choice fields named `status` and `kind` in the timeline serializer collided with other apps' enums and are plain strings.
4. **Git Bash path mangling** turned `/app/schema.yml` into a Windows path in `docker compose run`; the `types:` commands were run from PowerShell.
5. **`ruff format assistant`** also reformatted a few of the MCP agent's files (whitespace only).
6. A `ruff format` pass on `tests/test_permission_matrix.py` is the only change to existing lines there besides my rows.
7. The OpenAI `Response` type in SDK 3.46 requires `cache_write_tokens` in `input_tokens_details`; the fake in the tests includes it.
8. Existing Vitest suites needed two extra mocked requests (`GET /api/ai/keys/` and `GET /api/labs/lab1/ai-policy/`) in `AiAccess.test.tsx`; nothing else changed in them. The header button makes no request until the drawer is opened.

### Tests

- Backend (`TEST_DB_NAME=test_b5`, scoped; both SDKs replaced at the client boundary, see `assistant/tests/fakes.py`, no network): `test_assistant.py` (loop with three parallel calls and one failing, one message carries all results, thinking block replayed byte for byte, request parameters, fallback sent/not sent for Opus, Sonnet, user off and Haiku, refusal not replayed, max_tokens in a tool call, fallback marker, approve then run and audited `in_app`, decline, typing declines, read plus write in one turn, viewer cannot write even when approved, invalid arguments not offered, policy off/mcp give 403 for create, send and approve, policy changed mid-chat, who can change the policy, owner-only (member, viewer, outsider, lab admin), cross-lab, project scope validation, streaming in pieces with headers, unread response changes nothing, busy lock, lock released on close, no key, dangling call finished, nine provider error classes, bounded JSON retry, stale signature, step limit, model and tokens per answer, title, unknown models); `test_keys.py` (encrypted, last four only, one cheap call, rotation, bad shapes, rejected key not stored and provider text not shown, OpenAI check, per user, fallback setting, audit without the key, not in admin, error mapping); `test_openai.py`; `test_policy.py` (MCP); `test_ai_key_leaks.py`. 80 tests, plus the permission matrix file (all pass; new rows for 9 endpoints with fixtures in both labs and a Lab B secret in the cross-lab swap test).
- Vitest: `components/assistant/Assistant.test.tsx` (11: SSE parsing, setup states, policy off/mcp, streaming answer with model, tokens and cost, project scope, error with Try again, refusal notice, approval dialog showing tool and arguments, Approve sends true, Decline sends false, closing sends nothing), `pages/settings/AiKeys.test.tsx` (7: save and clear, last four only, rejection, remove, fallback checkbox, privacy text, policy radios for a PI and absent for a member). Full suite 261 pass, `tsc` clean, ESLint no errors.
- Types regenerated with the two `types:` commands; dev database migrated.

### How to test with a real key

1. Make a key: Anthropic Console > API keys (starts `sk-ant-`), and/or OpenAI dashboard > API keys. Fund the account a few dollars.
2. Sign in at http://localhost:5173 (seed: `pi@example.test`, password in `seed_pilot`). Settings > AI > "Assistant API keys": paste the key, "Check and save". It should show "Saved: ending ####" and the box should empty. A wrong key shows the provider's rejection and stores nothing.
3. Open a lab page, click Assistant in the header. Pick the provider and model (Haiku 5.5 or GPT-6 Luna are the cheapest for a first try). Ask "What projects are in this lab and which tasks are overdue?". You should see tool rows, streamed text with links to records, and a line like "claude-haiku-5-5 · 4,100 tokens in · 260 out · under $0.01".
4. Open a project page and ask about "this project": the chat is scoped to it.
5. Ask "Add a task called 'Order primers' to this project". A dialog names `create_task` with its arguments; nothing happens until Approve. Then check the task exists and Admin > Audit log shows "AI tool write" with `via: in_app`. Try Decline and try typing instead.
6. As a PI, Settings > AI > "AI assistants in <lab>": choose MCP only, then reopen the panel: it says the in-app assistant is off. Choose Off and a connected MCP client gets a 403.
7. Check the key never comes back: the Network tab responses for `/api/ai/keys/` hold only `last4`.
8. OpenAI path: it is the part verified only against the SDK's types and docs. If the first message fails with "could not process this request", look at the server log line and compare the request with `assistant/ai/openai_responses.py`; the model ids are in `assistant/ai/catalog.py`.
9. For a local run without spending money, the SDKs honour `ANTHROPIC_BASE_URL` and `OPENAI_BASE_URL`; point them at any server that speaks the streaming format.

### Not built, on purpose

No per-lab or shared keys; no usage limits or budgets (the provider's own console has them); no conversation sharing or export; no redaction of record text before sending; no web search or other server tools; no "regenerate" or edit-a-message (history is append-only); no title editing; no system-prompt editing by users; the consent and token pages still list a lab that turned AI off; no e2e (Playwright) spec; Gemini and other providers.


## Review fixes (security review of Run 5, D193-D204)

One agent, one pass. Every fix has a regression test, and each was confirmed by reverting the fix once and watching the test fail (the one exception is noted under "Honest limits"). Decisions are in `docs/DECISIONS.md` D193-D204.

### The three failing tests

- `core/tests/test_tenancy_lint.py::test_unscoped_only_in_allowed_files`: three test files used `.unscoped` to count rows (`assistant/tests/test_assistant.py`, `test_openai.py`, `provenance/tests/test_dmp.py`). I changed them to `Model.objects.for_lab(lab)` and left the allowlist alone: the lint is what keeps the rest of the code honest, a counting helper does not need the escape hatch, and widening it for tests is how a real bypass would later hide. (D204)
- `training/tests/test_training.py::test_weekly_digest` (`assert 5 == 2`) and `test_digest_silent_when_nothing_required`: they passed alone and failed in the full run. The permission matrix builds one session-scoped world that stays committed for the rest of the session, including a lab with training rows and three more managers, and the digest job (correctly) walks every lab. The `world` fixture in the training tests now points the job at its own lab. Reproduced with `pytest tests/test_permission_matrix.py training/tests/test_training.py`, failing before and passing after. No production code changed.

### Findings

1. **Exact redirect URIs (D193).** The allowlist is now a setting of exact URIs (`MCP_ALLOWED_REDIRECT_URIS`), applied at registration, when a CIMD document is read, and at every authorization (so old host-only client rows stop working). Defaults come from Claude's connector docs and OpenAI's plugin auth guide; **they are not verified against a live connect**, so the first real Claude and ChatGPT connection should confirm them. Loopback keeps any port.
2. **Recent re-authentication (D194).** Consent approval and token creation return allauth's own 401-with-flows body unless the session signed in or re-checked its password in the last 5 minutes; the SPA's existing `useReauth` prompt handles it (consent page and the Settings token form both wrapped). **Security events end grants (D195):** password change, password reset, TOTP removal and deactivation revoke every grant, audited per lab, with the reason stored so Settings can say why ("Claude stopped working because your password was changed").
3. **Stream exhaustion (D196).** Server-wide cap (10 of 24 threads by default), per-stream deadline (300 s, under the 330 s proxy timeouts), a heartbeat that keeps the slots alive, and the provider stream closed with the response. Slots instead of counters so a crashed worker cannot leak capacity. `deploy/docker-compose.prod.yml` and `deploy/Caddyfile` carry the settings and their relationship in comments.
4. **Prompt injection (D197-D199).** Record text is wrapped as `untrusted_content` with a note, tool descriptions and the in-app prompt say so, consent defaults to one lab and read only with warnings for more, the approval dialog shows resolved names (with unknown ids flagged in red) and the exact text to be posted, and assistant links are own-origin only with other addresses written out.
5. **SAML SLS (D201).** Route disabled. Setting `want_message_signed` was rejected because python3-saml then also demands the login response itself be signed, which D155 deliberately does not require.
6. **require-SSO bypass (D202).** Any verified address at a require-SSO institution forces that institution's SSO, for password (with a message), Google and other institutions' SAML. Tests: password with a secondary address, Google, and the provider matrix.
7. **LabGrantSerializer (D203).** `labs` is the viewed lab only.
8. **Client pruning (D200).** Daily job; the "Unverified app" label on consent is now a prominent alert.

### Trade-offs and honest limits

- **The residual prompt-injection risk is real (D199).** Wrapping is a mitigation. A lab member can still write text another member's AI app reads. For Claude and ChatGPT the client's own confirm-before-tool-call prompt is the remaining control and is outside our hands. Tell people who connect with write access to leave it on.
- **Reauth users with both SSO and a password** in a require-SSO domain cannot pass the password prompt (D156 refuses that password); they sign in through SSO again, which counts as recent. SSO-only accounts are never asked.
- **A fresh sign-in counts as a recent check**, so people are not asked twice in a minute. A stolen session cookie used more than 5 minutes after the real login is the case this blocks.
- **The disconnect test is weaker than it looks.** CPython closes an abandoned generator when its frame dies, so "closing the connection closes the provider stream" passes without the explicit `close()` calls I added; the deadline path does need them and its test fails without. I kept the explicit closes because they do not depend on garbage collection (and PyPy would).
- **Tool descriptions changed** (the untrusted-text sentence), so in-app conversations started before the deploy may report "start a new conversation" (D189).
- **SP metadata still lists the SLS URL** (allauth builds it). An IdP that tries it gets a 404; the IdP admin can drop it.
- **Existing sessions are not touched** by a new require-SSO setting; the check is at sign-in.
- **Tests that changed, and why.** `assistant/tests/test_tools.py::test_get_document_is_audited_as_a_view` reads `text["untrusted_content"]` (the new result shape). `pages/AiAccess.test.tsx` consent test now expects one lab ticked, read only, and the "Unverified app" alert (the intended new defaults) and `Assistant.test.tsx` uses an own-origin link in its answer fixture. Existing consent/PAT tests in `test_mcp.py` and `test_token_leaks.py` sign in through a helper (`assistant/tests/reauth.py`) that records a password sign-in, since `force_login` records none. No security expectation, matrix row or leak test was weakened.

### Tests added

- Backend: `assistant/tests/test_review_fixes.py` (47 cases: redirect URI matrix, CIMD rule, setting override, reauth for consent and tokens including the real allauth endpoint, a passwordless account, grants ended by each security event and listed to the owner, server/person caps, crashed-worker slot expiry, heartbeat, deadline, disconnect, pruning, lab view, approval names and preview), `core/tests/test_review_fixes5.py` (SLS 404, password/Google/other-institution require-SSO), `assistant/tests/test_tools.py` (untrusted wrapper in every text tool and the descriptions).
- Frontend: consent defaults, warnings, unverified alert and the reauth retry; token creation reauth; the "disconnected because" notice; approval dialog names/preview; own-origin links.

### Operator checklist

- Confirm `MCP_ALLOWED_REDIRECT_URIS` against a real Claude and a real ChatGPT connect; add exact URIs for any other AI app.
- Production env: `ASSISTANT_MAX_STREAMS` (default 10), `ASSISTANT_STREAM_DEADLINE` (300), `ASSISTANT_LOCK_TTL` (600). Keep the deadline below the 330 s gunicorn `--timeout` and Caddy read timeout, and the stream cap well below workers x threads (24).
- Run `manage.py migrate` (adds `assistant/0003`).
