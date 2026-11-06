# UI guide

Feels like Linear or Notion, not a university portal. Rules come from SPEC section 4. Build with the shared components below before writing anything custom.

## Rules: do and don't

**Layout**

- Do put every page inside `AppShell` (sidebar, breadcrumbs, content). Don't build page-level chrome.
- Do show item details in `DetailPanel` so people keep their place. Don't navigate away just to view a row.
- Do keep every item within three clicks. Add a command palette entry for anything important.

**Style**

- Do use the CSS variable tokens (`bg-background`, `text-muted-foreground`, `border-border`, `bg-primary`). Don't hard-code hex or Tailwind colour names like `bg-indigo-600`.
- Do use indigo (`primary`) for the main action per screen. Use `success`, `warning`, `danger` and `info` (with their `-foreground`) for status badges and buttons (D127), and `-text` variants for coloured text on white. Don't pick other colours.
- Do separate with spacing and tinted surfaces (`bg-muted`, `bg-sidebar`) before reaching for `border`. Don't use heavy shadows.
- Do test both themes. Contrast must stay at WCAG AA (4.5:1 for text).

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
- `StatusBadge` `status` string; known statuses get a tone, unknown ones are neutral. Add new ones to `TONES`.
- `ThemeToggle` light, dark, system segmented control in the header. `lib/theme.ts` applies it, keeps localStorage for first paint and saves it to the account (`preferences.theme`, D128).

Project sections are listed once, in `PROJECT_SECTIONS` (`lib/nav.ts`): a dropdown in the sidebar, and `TabNav` tabs below `md` (D205). `UnreadBadge` (`src/components/layout/`) takes `noun` for what it counts, and `TabNav` tabs take an optional badge.

Layout (`src/components/layout/`): `AppShell` (sidebar, breadcrumbs, `Toaster`, palette), `Sidebar` (lab switcher, projects, nav), `CommandPalette` (Ctrl/Cmd+K or Ctrl/Cmd+F; the browser keeps Ctrl+F in text fields, editors and the PDF viewer via `data-native-find`, D130), `UnreadBadge` (D131). Signed-out pages use `LandingHeader`, `HeroText` and `Features` from `pages/LandingPage` (D129).

Primitives (`src/components/ui/`, shadcn style): button, input, textarea, label, select, dialog, sheet, dropdown-menu, badge, skeleton, sonner, command, tooltip, separator, table. Add new ones only when a page needs them, and keep them in this style.

Command palette: call `useRegisterCommands(useMemo(() => [{ id, label, group, onSelect }], [deps]))` in a page. It unregisters on unmount. Memoize the array.

## Spacing and typography

- Spacing uses the 4px Tailwind scale. Between sections `gap-8`, between related items `gap-2` to `gap-4`, card and panel padding `p-6`, page padding `px-8 py-6`. Page content max width is `max-w-5xl`.
- Font is Inter then the system font. Page title `text-2xl font-semibold`, section title `text-base font-semibold`, body `text-sm`, hint and meta `text-xs text-muted-foreground`. Use two weights only: 400 and 500/600.
- Radius is `rounded-md` (8px) for controls, `rounded-lg` (12px) for panels and tables. Button variants: default, secondary, outline, ghost, success, warning, destructive; badge variants add info.

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
