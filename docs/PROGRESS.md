# Progress log

- 2026-11-04: Plan and decisions written. GNU make installed via winget.
- P0.2 done (haiku): frontend skeleton; lint, format, typecheck, test, build pass. TS pinned 5.9.
- P0.1 done (haiku): backend skeleton, Django 5.2, checks pass on host py3.13; Docker build pending P0.3.
- P1.0 done (opus): ARCHITECTURE.md + D18-D33. Human to confirm D25, D27, D28.
- P0.3 done (haiku): compose, Makefile, license scripts. Orchestrator swapped jsdom for happy-dom (MIT-0 transitive). Phase 0 accepted: make dev up, make test exit 0.
- Phase 0 committed. Started P1.1 (sonnet) and P2.4 (sonnet, parallel). permissions.py + audit core folded into P1.1 because Phase 1 endpoints need them.
- P2.4 done (sonnet): shadcn setup, 8 shared components, app shell, command palette, UI.md; 5 tests pass, licenses pass. Gaps: sidebar not responsive, lab switcher inert.
- P1.1 done (sonnet): tenancy, permissions.py, audit service, Phase 1 models; 98 backend tests pass.
- P1.4 done (sonnet): auth pages, TOTP, create lab, members/invites, accept invite; 21 frontend tests. Added qrcode (MIT). Reauth prompt not built. Integration check pending P1.2.
- P1.2 done (sonnet): allauth headless + MFA, Phase 1 API, matrix (135 cases + cross-lab swap). ~280 backend tests. Orchestrator smoke test through Vite proxy passed end to end; set ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION=True. Phase 1 accepted.
- P2.5 done (haiku): make types / types-check, openapi-typescript (MIT); api-types.ts aliases generated schema.
- P2.1-P2.3 done (sonnet): audit-events API (cursor, filters), coverage tests for 11 actions, ad hoc permission lint test, matrix row. make test green. Checkpoint commit before security review.
- Audit log page done (sonnet): 25 frontend tests. Follow-up: audit-events filter params missing from OpenAPI schema (needs extend_schema). Untracked tsbuildinfo.
- P2.6 security review (opus): 0 cross-lab leaks today; 8 issues (1 high-latent, 4 medium, 3 low). Decisions D38-D41. Sent to sonnet for fixes.
- P2.7 done (sonnet): all 8 review issues fixed with regression tests (verified failing pre-fix). make test green, smoke test green. Phase 2 accepted.
- Phase 2 committed. Phase 3 started: P3.1 (sonnet) and P3.2+P3.3 combined (sonnet, same app) in parallel.
- P3.2+P3.3 done (sonnet): documents/revisions/409/restore, attachments with lab-prefix storage, authenticated download, notice ack audit. 13 matrix rows. Enum name collision (from projects) relayed to P3.1 agent.
- P3.1 done (sonnet): projects, members, deadlines, tasks, reorder; enum overrides. ~47 matrix rows. Known issue: task assignee not re-checked after losing project access. Checkpoint commit.
