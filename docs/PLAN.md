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
| P4.5 | Security review gate + fixes | opus / high, sonnet / medium | done |

## Phase 5. Ethics and retention
| ID | Task | Model / effort | Status |
|---|---|---|---|
| P5.1 | Backend: EthicsApproval, reminders (60/30/7), notifications, beat schedule | sonnet / medium | done |
| P5.2 | Backend: retention fields, daily review job (never deletes) | sonnet / medium | done |
| P5.3 | Frontend: ethics pages, notifications, retention review | sonnet / medium | done |
| P5.4 | Security review gate + fixes | opus / high, sonnet / medium | done |

## Phase 6. Handover (stretch)
| ID | Task | Model / effort | Status |
|---|---|---|---|
| P6.1 | Handover report backend + frontend | sonnet / medium | done |

## Wrap-up
| ID | Task | Model / effort | Status |
|---|---|---|---|
| W.1 | Playwright click-through + screenshots to `docs/screenshots/` | sonnet / medium | done |
| W.2 | `docs/HANDOFF.md` | orchestrator | done |

---

# Plan: Build Run 2

Same status values. Model and effort follow orchestrator section 8. Shared-tree rules: each agent tests with its own `TEST_DB_NAME` (D58); new audit actions and notification kinds already exist (D59).

## Setup (orchestrator)
| ID | Task | Model / effort | Status |
|---|---|---|---|
| S.1 | Section 1 decisions in DECISIONS.md, backend deps (D60), MIT-0 in the Python license check, audit and notification migrations | orchestrator | done |

## Wave 1 (parallel)
| ID | Task | Model / effort | Status |
|---|---|---|---|
| A1 | Unassign open tasks on access loss, audit, notify leads, handover section | sonnet / medium | done |
| A2 | DB-level lab consistency: composite FKs, M2M triggers, pre-checks, guard test | sonnet / high | done |
| A3 | UI polish (plurals, relative dates, duplicate entry, sidebar drawer, mobile e2e) and D34 jsdom switch | haiku / low | done |
| B1 | Google sign-in backend: provider config, linking rules, any-verified-email invites (D25), `/accounts/` proxy | opus / high | done |
| C1 | Email service `core/email.py`, anymail config, route every email, export notice (D28) | sonnet / medium | done |
| D1 | Integration framework design and security core: registry, models, MultiFernet tokens, HTTP client, OAuth2 connect flow, token-leak test | opus / high | done |

## Wave 2
| ID | Task | Model / effort | Status |
|---|---|---|---|
| B2 | Google sign-in UI: buttons, connected accounts, email addresses in account settings | sonnet / medium | done |
| C2 | HTML email templates with the accent colour | haiku / low | done |
| B3 | Security review: Phase B | opus / high | done |
| B4 | Fix Phase B review findings | sonnet / medium | done |
| D2 | Integration endpoints, permissions, matrix, lifecycle, handover links, Integrations page | sonnet / medium | done |
| D3 | Security review: Phase D | opus / high | done |
| D4 | Fix Phase D review findings | sonnet / medium | done |

## Wave 3
| ID | Task | Model / effort | Status |
|---|---|---|---|
| E1 | Google Drive: drive.file, Picker, links on Files and research records, refresh job, dataset provenance | sonnet / medium | done |
| E2 | Security review: Phase E | opus / high | doing |
| F1 | Production Dockerfile, `/healthz`, reverse proxy example, prod settings checklist test, DEPLOY.md | haiku / low | done |
| W2 | Screenshots, HANDOFF.md | sonnet / medium, orchestrator | todo |
