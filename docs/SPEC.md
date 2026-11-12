# Spec: Research Lab Platform, Build Run 1

(Copied from the orchestrator prompt. Subagent briefs refer to sections by number.)

Where the product goes next (everything in one place, the Claude side panel, analysis, MATLAB) is in [VISION.md](VISION.md).

## 1. What we are building

A browser-based workspace for research labs, starting with human-participant labs (psychology, neuroscience, clinical, social science). It is closed source and paid. A PI pays for the lab on a tier set by lab size.

The core idea: a lab's work stays connected and understandable after a student leaves. Papers inform decisions. Decisions lead to analyses. Analyses use specific dataset versions and produce results. Results go into manuscripts. The platform records those links.

The platform does **not** store raw participant data. Labs keep raw data in approved institutional systems. We store project metadata, documents, notes, analysis outputs and anonymized results, plus pointers to where datasets live.

## 2. Scope for this run

**Phase 0. Repo and tooling**
- Monorepo: `backend/` (Django) and `frontend/` (React).
- Docker Compose for local dev: Postgres, Valkey, backend, worker, frontend.
- Linting and formatting: ruff and black for Python, ESLint and Prettier for TypeScript.
- A `make test` that runs everything. A `make dev` that starts everything.
- A license check script that fails if any dependency is not on the allowlist (section 5).
- Acceptance: `make dev` brings up a blank app. `make test` passes. The license check passes.

**Phase 1. Tenancy, accounts and roles**
- Models: `Institution` > `Lab` > `Project`. Every lab belongs to an institution. Create one placeholder institution for now.
- `User`, `LabMembership` (role: `pi`, `lab_admin`, `member`, `viewer`) and `ProjectMembership` (role: `lead`, `contributor`, `viewer`).
- Sign-up creates a user. A user creating a lab becomes its PI. A PI or lab admin invites researchers by email. The invite link expires after 7 days.
- Auth with django-allauth: email and password, plus optional TOTP MFA. Keep auth behind one module so institutional SSO (SAML) can be added later.
- Every table that holds lab data has a `lab_id`. Every query goes through a lab-scoped manager. No view or serializer touches lab data without it.
- Acceptance: Two labs exist in tests. No user in lab A can read, list, search or download anything from lab B through any endpoint.

**Phase 2. Permissions and audit log**
- One permission module (`backend/core/permissions.py`) that every endpoint, background job and future search or AI feature uses. No ad hoc permission checks scattered through views.
- Explicit permissions for sensitive actions: `manage_members`, `export`, `view_audit_log`, `manage_billing`, `delete_project`.
- An append-only `AuditEvent` table: who, what action, which object, when. No IP addresses (D266). Log views of documents, downloads, exports, membership changes, permission changes and deletions.
- **Permission test matrix.** A parametrized test that hits every API endpoint as every role (plus anonymous and other-lab user) and checks the expected allow or deny. When a new endpoint is added, the test fails until the endpoint is added to the matrix. This is the gate for all later phases.
- Acceptance: The matrix covers 100% of endpoints and passes. Audit events are written for the listed actions.

**Phase 3. Projects, tasks and documents**
- Project page: description, members, status, deadlines.
- Tasks: title, assignee, due date, status, linked project. A simple list and board view.
- Documents: rich-text notes using **BlockNote core only** (`@blocknote/core`, `@blocknote/react`, `@blocknote/mantine` or `@blocknote/shadcn`). Save the content as JSON on the server.
- Revisions: every save creates a `DocumentRevision` row. Users can view old revisions and restore one. No real-time collaboration in this run. If two people edit at once, the later save gets a clear "this document changed since you opened it" warning instead of silently overwriting.
- File attachments to projects, stored through django-storages. Local filesystem in dev, S3-compatible in prod. One storage prefix per lab.
- PDF viewing with PDF.js. No PDF editing in this run.
- On every file upload, show a short notice: "Do not upload participant identifiers. Upload only anonymized or aggregate data." Log that the user acknowledged it.
- Acceptance: Create, edit, revise and restore a document. Upload and view a PDF. The permission matrix still passes.

**Phase 4. Provenance links (the core feature)**
- `DatasetRecord`: name, where it lives (free text plus URL), who controls access, version label, optional checksum. No data is stored, just the pointer.
- `Analysis`: title, description, code reference (repo URL plus commit hash, or a file attachment), the dataset version(s) it used, who ran it, when.
- `Result`: title, summary, figures or tables as attachments, the analysis that produced it.
- `Decision`: a short record of a choice the lab made, with links to supporting documents or papers.
- `ManuscriptLink`: a manuscript (title, link to Overleaf or a Google Doc, status) and which results it uses.
- A project **lineage view**: a clean visual graph showing dataset → analysis → result → manuscript, with decisions attached where they apply. Clicking a node opens its detail panel.
- Acceptance: In the pilot seed data, a user can trace one manuscript result back to its exact dataset version and code commit in under three clicks.

**Phase 5. Ethics tracking and retention**
- `EthicsApproval`: approval number, board, title, linked projects, approval date, expiry date, status, attached documents.
- Reminders at 60, 30 and 7 days before expiry, to the project leads and the PI. In-app notifications now. Email sending can be stubbed with a console backend.
- Retention fields on projects and documents: `retain_until` date and a retention policy note. A daily job lists items past their retention date for the PI to review. **Never auto-delete.**
- Acceptance: Seed an approval expiring in 25 days and confirm the right reminders appear. The retention job lists the right items.

**Phase 6. Handover report (stretch)**
- On a project or member page, a "Generate handover" button. It produces a report of everything the person owns or leads: open tasks, documents, analyses, results, datasets they control, ethics approvals they are named on, and anything with no other owner.
- Acceptance: The report shows correct items for a seeded departing student.

**Out of scope for this run:** AI features, real-time collaboration, PDF editing, LaTeX compilation, Google Drive or SharePoint sync, REDCap or Qualtrics integration, billing and payments, funding, recruitment, participant records, deployment to any cloud.

## 3. Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, Django 5.x, Django REST Framework |
| Database | PostgreSQL 16 |
| Background jobs | Celery with Valkey as the broker (not Redis, for licensing) |
| Auth | django-allauth (email, password, TOTP MFA) |
| File storage | django-storages, local in dev, S3-compatible in prod |
| Frontend | React 18+, TypeScript (strict), Vite |
| Data fetching | TanStack Query |
| Routing | React Router |
| UI | Tailwind CSS and shadcn/ui (Radix primitives) |
| Editor | BlockNote core packages only |
| PDF | PDF.js for viewing, pdf-lib later for forms |
| Graph view | React Flow (`@xyflow/react`) |
| API contract | OpenAPI schema from drf-spectacular, TypeScript types generated from it |
| Tests | pytest and pytest-django for backend, Vitest and Testing Library for frontend, Playwright for a few end-to-end flows |

One backend application with internal apps (`core`, `labs`, `projects`, `documents`, `provenance`, `ethics`, `audit`). No microservices.

## 4. Frontend: clean and intuitive

The users are researchers who are tired of clunky academic software. The UI should feel like Linear or Notion, not like a university portal.

- **Layout.** Left sidebar with lab switcher at the top, then projects. Main area for content. A slide-over detail panel on the right for viewing items without leaving the page.
- **Navigation depth.** Any item reachable in three clicks or fewer. Breadcrumbs on every page.
- **Command palette** (Cmd/Ctrl+K) for jumping to projects, documents and actions.
- **Visual style.** Neutral greys, white surfaces, one accent colour. Inter or the system font. Generous spacing. Subtle borders over heavy shadows. Light and dark mode.
- **Empty states.** Every empty list explains what goes there and has one clear button to add the first item. No blank screens.
- **Feedback.** Loading skeletons, not spinners on whole pages. Toasts for saves. Inline validation on forms. Clear, human error messages.
- **Plain language.** "Datasets", "Analyses", "Results", "Ethics approvals". No internal jargon like "entities" or "nodes" in the UI.
- **Accessibility.** Keyboard navigable, visible focus states, WCAG AA contrast, labels on every input.
- **Consistency.** Build a small set of shared components first (page header, data table, empty state, detail panel, form field, status badge) and use them everywhere.

## 5. Licensing rules (closed source)

- Allowed dependency licenses: MIT, BSD-2, BSD-3, Apache-2.0, ISC, MPL-2.0 (used unmodified), PostgreSQL, Python Software Foundation. Extended by D2 in DECISIONS.md.
- Banned: GPL, AGPL, LGPL in frontend bundles, SSPL, BUSL, any "source available" or non-commercial license.
- **Never install `@blocknote/xl-*` packages.** Do not read, copy or adapt code from the BlockNote XL packages or any GPL or AGPL repo. If we need a feature like PDF or Word export, build it from scratch or on an allowed library.
- Do not modify files inside BlockNote's own packages. Extend it with our own components.
- Do not copy code from Stack Overflow or GitHub snippets without checking the license.
- The license check script from Phase 0 runs in `make test`.

## 6. Data and security rules

- The platform holds no raw participant data. The upload notice in Phase 3 is required.
- All lab data is lab-scoped (Phase 1). Cross-lab leaks are the worst possible bug.
- All sensitive actions go through the permission module and write audit events.
- Secrets come from environment variables. Commit a `.env.example`, never a real `.env`.
- Passwords hashed with Django defaults (Argon2 if available). CSRF on. Secure cookie settings ready for prod.
- File downloads go through an authenticated endpoint that checks permissions. Never serve user files from a public URL.
- Seed data must be obviously fake. No real names, emails or study details.

## 10. Hard stops (apply to every agent)

Stop and report instead of proceeding if you would need to: create an account or use a paid service; deploy or push to a remote; add a dependency outside the license allowlist; store real personal data; or weaken a permission check to make a test pass.
