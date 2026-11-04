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
