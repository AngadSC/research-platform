# UI guide

Bold and high contrast, not a university portal: a dark ink sidebar, an electric primary, and a colour of its own for each project (D76). Rules come from SPEC section 4. Build with the shared components below before writing anything custom.

## Rules: do and don't

**Layout**

- Do put every page inside `AppShell` (sidebar, breadcrumbs, content). Don't build page-level chrome.
- Do show item details in `DetailPanel` so people keep their place. Don't navigate away just to view a row.
- Do keep every item within three clicks. Add a command palette entry for anything important.

**Style**

- Do use the CSS variable tokens (`bg-background`, `text-muted-foreground`, `border-border`, `bg-primary`). Don't hard-code hex or Tailwind colour names like `bg-indigo-600`.
- Do use `primary` for the main action on a screen. Lime (`--sidebar-highlight`) means "you are here" and appears only on the sidebar and brand mark.
- Do use the `vivid` colours only to identify a project or person, through `vivid(id)` from `lib/identity.ts`, with `text-on-vivid` on top. Don't use them for status: that is what `success`, `warning` and `destructive` are for.
- Do wrap anything on the dark sidebar colour in `.sidebar-scope`. It redefines the tokens, so shared components work there unchanged.
- Do separate with `border`. Don't use heavy shadows.
- Do test both themes. Contrast must stay at WCAG AA (4.5:1 for text, 3:1 for field edges and focus rings).

**States**

- Do show `DataTable loading` skeletons while fetching. Don't show a full-page spinner.
- Do give every empty list an `EmptyState` with one primary button. Don't leave a blank area.
- Do confirm saves with `toast.success("Saved")` (from `sonner`). Don't use `alert()`.
- Do validate inline with `FormField error`. Write errors a person can act on ("Enter a title"), never "400 Bad Request".

**Accessibility**

- Do label every input (use `FormField`). Don't use placeholders as labels.
- Do keep visible focus rings (built into the primitives). Don't add `outline-none` without a ring replacement.
- Do make clickable rows keyboard reachable (`DataTable onRowClick` handles Enter and Space). Don't put click handlers on plain `div`s.
- Do give icon-only buttons an `aria-label`.

## Component inventory

Shared (`src/components/shared/`):

- `PageHeader` title, description, `actions` (buttons, right side), optional `breadcrumbs` override.
- `Breadcrumbs` `items: {label, to?}[]`; the shell already renders them from route `handle.crumb`.
- `DataTable` `columns`, `rows`, `getRowKey`, `loading`, `empty` (an `EmptyState`), `onRowClick`.
- `EmptyState` `icon`, `title`, `description`, `action` (one `Button`).
- `DetailPanel` `open`, `onOpenChange`, `title`, `description`; right slide-over, Escape closes, focus trapped.
- `FormField` `label`, `hint`, `error`; child is a function: `{(p) => <Input {...p} />}`.
- `UnreadBadge` `count`; hidden at zero, shows 99+ above that, reads out as "3 unread messages".
- `StatusBadge` `status` string; known statuses get a solid tone, unknown ones are neutral. Add new ones to `TONES`. `StatusPill` is the white version for a coloured banner.
- `ThemeToggle` light, dark, system; stored in localStorage (`lib/theme.ts`).

Layout (`src/components/layout/`): `AppShell` (sidebar, breadcrumbs, `Toaster`, palette), `Sidebar` (lab switcher, projects with their section dropdowns, nav), `BrandMark`, `CommandPalette` (Ctrl/Cmd+K). A project's sections are listed once, in `PROJECT_SECTIONS` (`lib/nav.ts`); they appear in the sidebar dropdown, and as pills below `md`, where the sidebar is a drawer.

Primitives (`src/components/ui/`, shadcn style): button, input, textarea, label, select, dialog, sheet, dropdown-menu, badge, skeleton, sonner, command, tooltip, separator, table. Add new ones only when a page needs them, and keep them in this style.

Command palette: call `useRegisterCommands(useMemo(() => [{ id, label, group, onSelect }], [deps]))` in a page. It unregisters on unmount. Memoize the array.

## Spacing and typography

- Spacing uses the 4px Tailwind scale. Between sections `gap-8`, between related items `gap-2` to `gap-4`, card and panel padding `p-6`, page padding `px-8 py-6`. Page content max width is `max-w-5xl`.
- Font is Inter then the system font. Page title `text-3xl font-bold`, project banner title `text-2xl font-bold`, section title `text-base font-semibold`, body `text-sm`, hint and meta `text-xs text-muted-foreground`. Use weights 400, 500/600 and, for titles only, 700.
- Radius is `rounded-md` for controls, `rounded-lg` for panels and tables.

## Add a page

1. Create `src/pages/FooPage.tsx`. Start with `<PageHeader title=... />`, then content.
2. Fetch with a TanStack Query hook. Pass `isLoading` to `DataTable`, and an `EmptyState` as `empty`.
3. Add the route as a child of the layout route in `src/App.tsx` with `handle: { crumb: "Foo" }`. Nested routes get nested crumbs.
4. Add a sidebar link in `src/lib/nav.ts` if it is top level.
5. Register palette commands for its main actions.
6. Write a test beside it. Query by role and label, as the user would.

## Vocabulary

Use these words in all visible text:

| Say                | Never say                      |
| ------------------ | ------------------------------ |
| Datasets           | entities, records, objects     |
| Analyses           | jobs, runs, pipelines          |
| Results            | outputs, artifacts             |
| Ethics approvals   | compliance items, consents     |
| Projects, Labs     | workspaces, tenants, orgs      |
| Connected to       | linked nodes, edges, lineage   |

Never show "entity", "node", "UUID", "null", stack traces or HTTP codes. The product name comes from `APP_NAME` in `lib/constants.ts`.
