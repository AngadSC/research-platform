# Plan: Build Run 1

Status: `todo` | `doing` | `done` | `failed` | `escalated`. Model/effort per orchestrator section 7.

## Phase 0. Repo and tooling
| ID | Task | Model / effort | Status |
|---|---|---|---|
| P0.1 | Backend skeleton: Django project `config`, empty apps, settings from env, pyproject (ruff, black, pytest), requirements, Dockerfile, `.env.example` | haiku / low | done |
| P0.2 | Frontend skeleton: Vite + React + TS strict, Tailwind, ESLint, Prettier, Vitest, blank app, Dockerfile | haiku / low | done |
| P0.3 | docker-compose (postgres, valkey, backend, worker, beat, frontend), Makefile (`dev`, `test`, `lint`), license check script, `.gitignore` | haiku / low | done |
| P0.4 | Acceptance: `make dev`, `make test`, license check. Commit. | orchestrator | done |

## Phase 1. Tenancy, accounts, roles
| ID | Task | Model / effort | Status |
|---|---|---|---|
| P1.0 | `docs/ARCHITECTURE.md`: data model, tenancy, lab-scoped manager, permission module design, endpoint list | opus / high | done |
| P1.1 | Tenancy core: base model/manager, permissions.py, AuditEvent + service, Phase 1 models, unit tests | sonnet / medium | done |
| P1.2 | Auth module (allauth headless: email/password, TOTP), signup, create lab, invites (7-day expiry), APIs | sonnet / medium | done |
| P1.3 | (folded into P1.2 with matrix, D36) Cross-lab isolation tests (two labs, every endpoint) | sonnet / medium | done |
| P1.4 | Frontend: login, signup, create lab, accept invite pages | sonnet / medium | done |

## Phase 2. Permissions and audit
| ID | Task | Model / effort | Status |
|---|---|---|---|
| P2.1 | (core built in P1.1) wire sensitive permissions + audit into every endpoint | sonnet / medium | done |
| P2.2 | AuditEvent (append-only) + logging for listed actions | sonnet / medium | done |
| P2.3 | (started in P1.2) extend matrix to Phase 2 endpoints Permission matrix test (enumerates URL resolver, fails on unlisted endpoints) | sonnet / medium | done |
| P2.4 | Shared UI components, app shell (sidebar, lab switcher, breadcrumbs, detail panel), `docs/UI.md` | sonnet / medium | done |
| P2.5 | OpenAPI schema + generated TS types (`make types`) | haiku / low | done |
| P2.6 | Security review gate | opus / high | done |
| P2.7 | Fix review findings | sonnet / medium | done |

## Phase 3. Projects, tasks, documents
| ID | Task | Model / effort | Status |
|---|---|---|---|
| P3.1 | Backend: project fields, tasks API | sonnet / medium | done |
| P3.2 | Backend: documents (BlockNote JSON), revisions, restore, version conflict (409) | sonnet / medium | done |
| P3.3 | Backend: attachments, per-lab storage prefix, authenticated download, upload acknowledgment audit | sonnet / medium | done |
| P3.4 | Frontend: project page, task list + board | sonnet / medium | done |
| P3.5 | Frontend: document editor, revisions, restore, conflict warning | sonnet / medium | done |
| P3.6 | Frontend: attachments, upload notice, PDF.js viewer | sonnet / medium | done |

## Phase 4. Provenance
| ID | Task | Model / effort | Status |
|---|---|---|---|
| P4.1 | Backend: DatasetRecord, Analysis, Result, Decision, ManuscriptLink + lineage endpoint | sonnet / medium | done |
| P4.2 | Pilot seed data (obviously fake) | haiku / low | done |
| P4.3 | Lineage graph view (React Flow) + detail panel | sonnet / high | done |
| P4.4 | Frontend: provenance list/detail/forms, command palette | sonnet / medium | done |
| P4.5 | Security review gate + fixes | opus / high, sonnet / medium | doing |

## Phase 5. Ethics and retention
| ID | Task | Model / effort | Status |
|---|---|---|---|
| P5.1 | Backend: EthicsApproval, reminders (60/30/7), notifications, beat schedule | sonnet / medium | todo |
| P5.2 | Backend: retention fields, daily review job (never deletes) | sonnet / medium | todo |
| P5.3 | Frontend: ethics pages, notifications, retention review | sonnet / medium | todo |
| P5.4 | Security review gate + fixes | opus / high, sonnet / medium | todo |

## Phase 6. Handover (stretch)
| ID | Task | Model / effort | Status |
|---|---|---|---|
| P6.1 | Handover report backend + frontend | sonnet / medium | todo |

## Wrap-up
| ID | Task | Model / effort | Status |
|---|---|---|---|
| W.1 | Playwright click-through + screenshots to `docs/screenshots/` | sonnet / medium | todo |
| W.2 | `docs/HANDOFF.md` | orchestrator | todo |
