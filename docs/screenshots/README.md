# Screenshots

Regenerate with `make screenshots` (dev stack up and seeded). 1440x900, light mode, as `pi@` unless noted.

- 01-login.png: login page, logged out
- 02-lab-home.png: lab home with the projects list
- 03-project-overview.png: project overview
- 04-task-board.png: task board
- 05-task-list.png: task list
- 06-documents-list.png: documents list
- 07-document-revisions.png: document editor with the revisions panel open
- 08-files.png: files tab
- 09-upload-dialog.png: upload dialog with the participant-data notice
- 10-pdf-viewer.png: PDF viewer
- 11-datasets.png: research datasets list
- 12-analysis-detail.png: analysis detail
- 13-lineage.png: lineage graph
- 14-lineage-panel.png: lineage with a result selected and its panel open
- 15-ethics-list.png: ethics approvals list
- 16-ethics-detail.png: ethics approval detail
- 17-notifications.png: notifications
- 18-retention.png: retention review
- 19-members.png: members page
- 20-audit-log.png: audit log
- 21-handover.png: handover report for student@
- 22-command-palette.png: command palette (Ctrl+K)
- 23-empty-state.png: empty state, a new project with no tasks
- 24-dark-lineage.png: lineage graph, dark mode
- 25-dark-project-overview.png: project overview, dark mode
- 26-viewer-document.png: document as `viewer@` (read-only)
- 27-integrations-pi.png: Integrations page as `pi@` (all provider categories, everyone's connections)
- 28-integrations-lead.png: Integrations page as `lead@` (own Drive connection)
- 29-security-settings.png: account security with Email addresses (Connected accounts shows only when Google sign-in is configured)
- 30-files-drive-links.png: Files tab with a Drive link, "Changed since linked" (as `lead@`)
- 31-dataset-drive-link.png: dataset record with a Drive link, "No longer available"
- 32-notifications-relative.png: notification bell list with relative times
- 33-lineage-panel-drive-link.png: lineage panel for a dataset with a Drive link
- 34-handover-sections.png: handover report for `lead@` with the external links section
- 35-mobile-drawer.png: mobile drawer open, 390x844
- 36-connect-api-key.png: API-key connect dialog (GitLab: address and token fields)
- 37-link-from-menu.png: "Link from..." menu open on a dataset
- 38-search-link-dialog.png: search link dialog with a result list (GitHub, on a dataset)
- 39-overleaf-paste-dialog.png: Overleaf paste-URL dialog (link and title) on a manuscript
- 40-palette-search.png: command palette showing lab-wide search results for "attention"
- 41-decision-references.png: decision with its References and the Zotero link
- 42-dataset-zenodo-link.png: dataset with a Zenodo link
- 43-analysis-github-link.png: analysis with the GitHub link (repo@commit)

Drive rows come from `seed_pilot` (fake connection, `example.invalid` URLs, no tokens).
GitHub, Overleaf, Zotero and Zenodo rows come from `seed_pilot` too (tokenless links, `.invalid` hosts, fake ids such as `example-lab-fake`), plus a tokenless GitHub connection for `pi@` so the search dialog opens. No connected provider can search offline, so 38 mocks the search reply in the browser (`page.route`); the two results are fake and the server never calls GitHub.

Run 4 (founder's change list; the dark ones switch the header toggle, because the account theme beats localStorage, D128):

- 44-landing.png: signed-out landing page
- 45-overview-priorities-last-edited.png: project overview with deadline priorities and "Last edited"
- 46-workflow-funding.png, 47-workflow-ethics-ualberta.png (University of Alberta resources), 48-workflow-participants.png, 49-workflow-review.png: Workflow sub-tabs
- 50-tasks-coloured-board.png: coloured task board
- 51-task-drawer-thread-files.png: task drawer with attached document and thread
- 52-admin.png: Admin (lab details, onboarding, inventory, institution resources)
- 53-inventory.png: Inventory page
- 54-settings.png: Settings
- 55-unread-badge.png: unread badges on the bell, sidebar and lab switcher (notifications mocked)
- 56-dark-workflow-ethics.png, 57-dark-tasks-board.png: dark mode
