# Handoff: Build Run 1

All six phases are built, tested and committed on `main`. Nothing has been deployed or pushed anywhere. Everything below was checked on a local Docker stack using obviously fake seed data.

## What was built

| Phase | What works | Not finished |
|---|---|---|
| 0. Tooling | Monorepo, Docker Compose (Postgres 16, Valkey, backend, Celery worker and beat, frontend). `make dev`, `make test`, a license check, ruff, black, ESLint, Prettier | – |
| 1. Accounts | Institution > Lab > Project. Email and password sign-up with mandatory email verification, and optional TOTP two-factor login. Lab roles (PI, lab admin, member, viewer) and project roles (lead, contributor, viewer). Invites expire after 7 days and only work for the invited, verified email | No SSO yet (one module, `core/auth.py`, is ready for it). No re-authentication prompt |
| 2. Permissions and audit | Every check goes through `core/permissions.py`. The append-only audit log, which the database itself enforces, has a filterable UI. A test fails if a role is checked outside that module | – |
| 3. Projects, tasks, documents | Project pages, task list and board (drag or keyboard), BlockNote documents with revisions, restore and a "changed since you opened it" warning. Files are stored per lab and downloaded only through a permission-checked endpoint, with the participant-data notice on every upload. PDF.js viewer | Decision references can't be edited in the UI |
| 4. Provenance | Datasets (versioned pointers, no data), analyses (repo plus commit), results, decisions, manuscripts. Lineage graph with an upstream-chain panel and a list view for accessibility. JSON project export | Search across the whole lab |
| 5. Ethics and retention | Ethics approvals with files. Daily reminders at 60, 30 and 7 days that are never sent twice. In-app notifications. Per-approval **Restricted** switch (your request). Retention dates and a PI review page. Nothing is ever deleted automatically | Real email sending (console only) |
| 6. Handover | "Generate handover" on members and project pages, with a "No other owner" callout and print to PDF | – |

The spec's acceptance checks, all verified:
- **Phase 1:** a user in one lab can't reach another lab's data through any endpoint. The automated test swaps in another lab's IDs everywhere and expects "not found".
- **Phase 4:** a manuscript result traces back to its exact dataset version and code commit in **2 clicks** from the project page (Lineage tab, then the result).
- **Phase 5:** an approval expiring in 25 days produces exactly one 30-day reminder each for the PI, the lead and the lab admin. The retention scan flags the right items and deletes nothing.
- **Phase 6:** the seeded student's report lists their tasks and analysis, with their solo project under "No other owner".

## How to run it

One-time setup: Docker Desktop must be running, and `make` must be installed (`winget install ezwinports.make`, then open a new terminal).

```
make dev            # start everything; app at http://localhost:5173
make seed           # fake pilot lab (run once, with dev running)
make test           # lint, backend, frontend, type drift, license check
make e2e            # Playwright browser tests (dev running and seeded)
make screenshots    # refresh docs/screenshots/
make types          # regenerate TypeScript types from the API schema
make down           # stop; `docker compose down -v` wipes the dev database
```

Seed logins: `pi@`, `admin@`, `lead@`, `student@` and `viewer@` at `example.test`, all with password `seed-password-not-secret`.

## Test results

- **Backend:** 1,134 passed, 20 skipped. The skips are cross-lab swap cases for URLs that have no object ID.
- **Permission matrix:** covers 100% of API endpoints, about 86 endpoint and method rows across 9 personas (anonymous, other-lab user, and every lab and project role), for 844 test cases. A new endpoint fails the test until someone adds it. Each row's expected result was written by hand, not copied from what the code returns.
- **Frontend:** 86 Vitest tests. **Browser:** 9 Playwright tests. Licenses: 57 Python and 415 npm packages, all allowed.
- **Security reviews:** three fresh, independent reviews (after Phases 2, 4 and 5) found no cross-lab leak. They found 23 issues inside a lab, including 1 high. All are fixed with regression tests, and I spot-checked those tests by deliberately breaking the fixed code.

## Decisions a human should confirm

These are all in `docs/DECISIONS.md`, marked **[H]**.

1. **D2, D34. Licenses.** LGPL is allowed for the backend Postgres driver. MIT-0 is **not** allowed, so the tests use happy-dom instead of jsdom and cffi is pinned to an older version. Allowing MIT-0 would remove both workarounds.
2. **D12. Name and accent colour.** The name "Research Workspace" and the indigo accent are placeholders.
3. **D25.** An invite only works for the exact verified email it was sent to.
4. **D27, D56.** Ethics approvals are visible to the whole lab unless switched to Restricted (you confirmed this).
5. **D28.** Only the PI and lab admins can delete projects (a soft delete). Export is limited to the PI, lab admins and project leads.
6. **D51.** Lab admins also get ethics reminders and retention notices.
7. **D57.** In "No other owner", the PI and lab admins don't count as other owners.

## Known issues, most severe first

1. **Not production-ready yet.**
   - There is no deployment config.
   - The production reverse proxy **must** cap request body size (D53).
   - Downloads stream through Django, which holds a worker per download. The upgrade path is X-Accel-Redirect or short-lived signed URLs.
   - Email goes only to the console.
2. **Lab consistency is enforced in app code, not by database foreign keys** (D31). The lab-scope guard also can't catch an unscoped query used inside another query's filter. Tests cover today's code, but new code needs care.
3. **A task stays assigned to someone after they lose access to the project.**
4. **UI copy and polish:**
   - notifications say "day(s)" and show ISO dates
   - the command palette lists members twice
   - "Not Set" casing on the overview
   - a large gap on the ethics detail page
   - the sidebar doesn't collapse on small screens
5. `test_audit_api` failed once locally and passed on every run since. Watch it for flakiness.
6. **Dev-only leftovers:**
   - the dev database holds three junk "Empty project (screenshots)" projects; `docker compose down -v` and `make seed` reset it
   - the signup browser test reads the verification link from the Docker logs

## Suggested next tasks, in priority order

1. Confirm or change the [H] decisions above.
2. **Production readiness:**
   - deployment config with HTTPS
   - a body-size cap at the proxy
   - S3 storage settings
   - a real email provider
   - X-Accel-Redirect or signed-URL downloads
3. **Sign-in options:** Google sign-in and/or institutional SAML through allauth. The code is ready, but you need to create the Google or IdP OAuth client yourself.
4. Fix the UI copy issues in item 4 above, and make the sidebar responsive.
5. Enforce lab consistency in the database (composite foreign keys), and re-check task assignees when someone loses project access.
6. A lab-wide search endpoint for the command palette (D45).
7. Billing tiers by lab size (out of scope for this run).

## Agents used

31 subagents, with no escalations needed:
- **Opus:** 4 (architecture design, plus 3 security reviews)
- **Sonnet:** 22 (features, fixes, browser tests, screenshots)
- **Haiku:** 5 (scaffolding, type generation, seed data)

Plan, decisions and the progress log are in `docs/PLAN.md`, `docs/DECISIONS.md` and `docs/PROGRESS.md`. Design is in `docs/ARCHITECTURE.md`, UI rules in `docs/UI.md`, and screenshots in `docs/screenshots/`.
