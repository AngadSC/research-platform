import { mkdirSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { login, openProject, PROJECT } from "./helpers";

const DIR = "../docs/screenshots";
mkdirSync(DIR, { recursive: true });

const shot = async (page: Page, name: string) => {
  await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {}); // a stalled request must not block a screenshot
  await page.waitForTimeout(400);
  // The app scrolls inside <main>, so grow the viewport to fit instead of relying on fullPage.
  const h = await page.evaluate(() =>
    document.querySelector("[role=dialog]")
      ? 0
      : Math.max(
          document.documentElement.scrollHeight,
          ...Array.from(document.querySelectorAll("main, [class*=overflow-y]")).map(
            (e) => e.scrollHeight,
          ),
        ),
  );
  await page.setViewportSize({ width: 1440, height: Math.max(900, Math.min(h + 40, 4000)) });
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${DIR}/${name}.png`, fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });
};
/** Click a table row and wait for the detail page; a click that lands during a re-render is retried. */
const openRow = (page: Page, row: ReturnType<Page["getByRole"]>) =>
  expect(async () => {
    const before = page.url();
    await row.click({ timeout: 5000 });
    await expect(page).not.toHaveURL(before, { timeout: 5000 });
  }).toPass({ timeout: 30_000 });
const theme = (page: Page, t: "light" | "dark") =>
  page.addInitScript((v) => localStorage.setItem("theme", v), t);
/** Pick a theme with the header toggle: it saves to the account, which beats localStorage on sign-in (D128). */
const pick = async (page: Page, t: "Light" | "Dark") => {
  await page.getByRole("radio", { name: t }).click();
  await expect(page.locator("html")).toHaveClass(t === "Dark" ? /dark/ : /^(?!.*dark)/);
};
const base = (page: Page) => page.url().replace(/\/(overview|tasks|documents|files).*$/, "");
const lab = (page: Page) => page.url().match(/\/labs\/[^/]+/)![0];

/** Earlier `make e2e` runs leave e2e-*.pdf uploads on the Files tab; remove them so reruns match. */
const clearE2eUploads = async (page: Page) => {
  const del = page.getByRole("button", { name: /^Delete e2e-/ });
  while (await del.count()) {
    await del.first().click();
    await page.getByRole("button", { name: "Delete file" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
  }
};

test.beforeEach(async ({ page }) => theme(page, "light"));

test.describe("@screenshots", () => {
  test("logged out", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    await shot(page, "01-login");
  });

  test("pi flows", async ({ page }) => {
    await login(page, "pi");
    await expect(page.getByText(PROJECT).first()).toBeVisible();
    await shot(page, "02-lab-home");

    await openProject(page);
    const b = base(page);
    const l = lab(page);
    await shot(page, "03-project-overview");

    await page.goto(`${b}/tasks?view=board`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await shot(page, "04-task-board");
    await page.goto(`${b}/tasks?view=list`);
    await shot(page, "05-task-list");

    await page.goto(`${b}/documents`);
    await expect(page.getByText("Study protocol draft (FAKE)")).toBeVisible();
    await shot(page, "06-documents-list");
    await page.getByText("Study protocol draft (FAKE)").click();
    await expect(page.getByLabel("Document content")).toBeVisible();
    await page.getByRole("button", { name: "History" }).click();
    await page.getByRole("button", { name: /^Version 1\b/ }).click();
    await shot(page, "07-document-revisions");

    await page.goto(`${b}/files`);
    await expect(page.getByRole("button", { name: "Upload file" }).first()).toBeVisible();
    await clearE2eUploads(page);
    await shot(page, "08-files");
    await page.getByRole("button", { name: "Upload file" }).first().click();
    await expect(page.getByText(/Do not upload participant identifiers/)).toBeVisible();
    await shot(page, "09-upload-dialog");
    await page.keyboard.press("Escape");

    const open = page.getByRole("link", { name: "Open fake-protocol.pdf" }).first();
    if (await open.count()) {
      await open.click();
      await expect(page.locator("canvas")).toBeVisible();
      await page.waitForTimeout(1000);
      await shot(page, "10-pdf-viewer");
    }

    await page.goto(`${b}/workflow/data`);
    await expect(page.getByRole("table")).toBeVisible();
    await shot(page, "11-datasets");
    await page.goto(`${b}/workflow/analysis`);
    await page.getByRole("table").getByRole("row").nth(1).click();
    await expect(page.getByRole("navigation", { name: /breadcrumb/i })).toContainText("Analyses");
    await shot(page, "12-analysis-detail");

    await page.goto(`${b}/lineage`);
    const result = page.getByRole("button", { name: "Result: Reaction time effect (FAKE)" });
    await expect(result).toBeVisible();
    await shot(page, "13-lineage");
    await result.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await shot(page, "14-lineage-panel");

    await page.goto(`${l}/ethics`);
    await expect(page.getByRole("row", { name: /FAKE-IRB-2026-001/ })).toBeVisible();
    await shot(page, "15-ethics-list");
    await page.getByRole("row", { name: /FAKE-IRB-2026-001/ }).click();
    await expect(page.getByRole("heading", { name: /approval \(FAKE\)/ })).toBeVisible();
    await shot(page, "16-ethics-detail");

    await page.goto(`${l}/notifications`);
    await shot(page, "17-notifications");
    await page.goto(`${l}/retention`);
    await shot(page, "18-retention");
    await page.goto(`${l}/members`);
    await expect(page.getByRole("heading", { name: "Members" })).toBeVisible();
    await shot(page, "19-members");
    await page.goto(`${l}/audit-log`);
    await shot(page, "20-audit-log");

    await page.goto(`${l}/members`);
    await page.getByRole("link", { name: /Generate handover for student@example.test/ }).click();
    await expect(page.getByRole("heading", { name: /Handover: Sam Student/ })).toBeVisible();
    await shot(page, "21-handover");

    await page.goto("/");
    await expect(page.getByText(PROJECT).first()).toBeVisible();
    await page.keyboard.press("Control+k");
    await expect(page.getByRole("dialog")).toBeVisible();
    await shot(page, "22-command-palette");
    await page.keyboard.press("Escape");

    // Empty state: a project with nothing in it (created once, reused afterwards).
    const empty = "Empty project (screenshots)";
    await page.goto(l);
    // The sidebar lists every project; wait for it before deciding whether one exists.
    const side = page.locator("#app-sidebar");
    await expect(side.getByRole("link", { name: PROJECT })).toBeVisible();
    if (!(await side.getByRole("link", { name: empty }).count())) {
      await page.getByRole("button", { name: "New project" }).first().click();
      const d = page.getByRole("dialog");
      await d.getByLabel("Name").fill(empty);
      await d.getByRole("button", { name: "Save" }).click();
      await expect(side.getByRole("link", { name: empty })).toBeVisible();
    }
    await side.getByRole("link", { name: empty }).first().click();
    await expect(page).toHaveURL(/\/overview$/);
    await page.goto(page.url().replace(/\/overview$/, "/tasks"));
    await expect(page.getByText("No tasks yet")).toBeVisible();
    await shot(page, "23-empty-state");
  });

  test("run 2 screens", async ({ page }) => {
    await login(page, "pi");
    await openProject(page);
    const b = base(page);
    const l = lab(page);

    await page.goto(`${l}/settings/integrations`);
    await expect(page.getByRole("heading", { name: "Integrations", level: 1 })).toBeVisible();
    await expect(page.getByText("Lee Lead (FAKE)").first()).toBeVisible();

    await page.goto("/account");
    await expect(page.getByRole("heading", { name: "Email addresses" })).toBeVisible();
    // "Connected accounts" (Google) only renders when Google sign-in is configured; shown as is.
    await shot(page, "29-security-settings");

    await page.goto(`${b}/lineage`);
    await page
      .getByRole("button", { name: "Dataset: Attention task responses (FAKE)" })
      .last()
      .click();
    await expect(page.getByRole("dialog").getByText("No longer available")).toBeVisible();
    await shot(page, "33-lineage-panel-drive-link");

    await page.goto(`${l}/members`);
    await page.getByRole("link", { name: /Generate handover for lead@/ }).click();
    await expect(page.getByRole("heading", { name: /Handover: Lee Lead/ })).toBeVisible();
    await expect(page.getByText("attention-responses-export (FAKE).csv")).toBeVisible();
    await shot(page, "34-handover-sections");

    // The bell's list shows relative times ("3 hours ago").
    await page.goto(`${l}`);
    await page.getByRole("button", { name: /^Notifications, \d+ unread/ }).click();
    await expect(page.getByText(/ ago/).first()).toBeVisible();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${DIR}/32-notifications-relative.png` });
  });

  test("run 2 screens as lead", async ({ page }) => {
    await login(page, "lead");
    await openProject(page);
    const b = base(page);
    const l = lab(page);

    await page.goto(`${l}/settings/integrations`);
    await expect(page.getByRole("heading", { name: "Integrations", level: 1 })).toBeVisible();
    await expect(page.getByText(/lead@example\.invalid/).first()).toBeVisible();
    await shot(page, "28-integrations-lead");

    await page.goto(`${b}/files`);
    await expect(page.getByText("Changed since linked")).toBeVisible();
    await shot(page, "30-files-drive-links");

    await page.goto(`${b}/workflow/data`);
    await page.getByRole("row", { name: /v2/ }).click();
    await expect(page.getByText("No longer available")).toBeVisible();
    await shot(page, "31-dataset-drive-link");

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${b}/overview`);
    await page.getByRole("button", { name: "Open navigation" }).click();
    await expect(page.locator("#app-sidebar")).toBeVisible();
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${DIR}/35-mobile-drawer.png` });
  });

  test("run 3 screens", async ({ page }) => {
    await login(page, "pi");
    await openProject(page);
    const b = base(page);
    const l = lab(page);

    await page.goto(`${l}/settings/integrations`);
    await expect(page.getByRole("heading", { name: "Integrations", level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "File storage" })).toBeVisible();
    await shot(page, "27-integrations-pi");
    await page.getByRole("button", { name: "Connect GitLab" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await shot(page, "36-connect-api-key");
    await page.keyboard.press("Escape");

    await page.goto(`${b}/workflow/data`);
    await openRow(page, page.getByRole("row", { name: /v1/ }));
    await expect(page.getByText("archived copy (FAKE)")).toBeVisible();
    await shot(page, "42-dataset-zenodo-link");
    await page.getByRole("button", { name: /Link from/ }).click();
    await expect(page.getByRole("menuitem", { name: /GitHub/ })).toBeVisible();
    await shot(page, "37-link-from-menu");

    // No connected search provider can answer offline, so the browser answers the search call.
    await page.route("**/integrations/github/search/**", (r) =>
      r.fulfill({
        json: [
          {
            id: "example-lab-fake/attention-data",
            title: "example-lab-fake/attention-data (FAKE)",
            subtitle: "Fake repository",
            modified: null,
          },
          {
            id: "example-lab-fake/rt-trimming",
            title: "example-lab-fake/rt-trimming (FAKE)",
            subtitle: "Fake repository",
            modified: null,
          },
        ],
      }),
    );
    await page.getByRole("menuitem", { name: /GitHub/ }).click();
    await expect(
      page.getByRole("dialog").getByText("example-lab-fake/rt-trimming (FAKE)"),
    ).toBeVisible();
    await shot(page, "38-search-link-dialog");
    await page.keyboard.press("Escape");

    await page.goto(`${b}/workflow/manuscript`);
    await openRow(page, page.getByRole("row").nth(1));
    await expect(page.getByText("Attention manuscript source (FAKE)")).toBeVisible();
    await page.getByRole("button", { name: /Link from/ }).click();
    await page.getByRole("menuitem", { name: /Overleaf/ }).click();
    await expect(page.getByLabel("Overleaf link")).toBeVisible();
    await shot(page, "39-overleaf-paste-dialog");
    await page.keyboard.press("Escape");

    await page.goto("/");
    await expect(page.getByText(PROJECT).first()).toBeVisible();
    await page.keyboard.press("Control+k");
    await page.getByRole("dialog").getByRole("combobox").fill("attention");
    await expect(page.getByRole("dialog").getByRole("option").nth(1)).toBeVisible();
    await shot(page, "40-palette-search");
    await page.keyboard.press("Escape");

    await page.goto(`${b}/workflow/review`);
    await openRow(page, page.getByRole("row").nth(1));
    await expect(
      page.getByText("Fake reference on response-time trimming (FAKE)").first(),
    ).toBeVisible();
    await shot(page, "41-decision-references");

    await page.goto(`${b}/workflow/analysis`);
    await openRow(page, page.getByRole("table").getByRole("row").nth(1));
    await expect(page.getByText("example-lab-fake/attention-analysis (FAKE)")).toBeVisible();
    await shot(page, "43-analysis-github-link");
  });

  test("dark mode", async ({ page }) => {
    await theme(page, "dark");
    await login(page, "pi");
    await pick(page, "Dark");
    await openProject(page);
    const b = base(page);
    await shot(page, "25-dark-project-overview");
    await page.goto(`${b}/lineage`);
    await expect(
      page.getByRole("button", { name: "Result: Reaction time effect (FAKE)" }),
    ).toBeVisible();
    await shot(page, "24-dark-lineage");
    await pick(page, "Light"); // leave the shared account as found
  });

  test("viewer read-only document", async ({ page }) => {
    await login(page, "viewer");
    await openProject(page);
    await page.goto(`${base(page)}/documents`);
    await page.getByText("Study protocol draft (FAKE)").click();
    await expect(page.getByLabel("Document content")).toBeVisible();
    await shot(page, "26-viewer-document");
  });

  test("run 4: landing, workflow, overview, tasks, admin, settings, dark", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("link", { name: "Register" }).first()).toBeVisible();
    await shot(page, "44-landing");

    await login(page, "pi");
    await openProject(page);
    await shot(page, "45-overview-priorities-last-edited");
    const b = base(page);
    for (const [slug, name] of [
      ["funding", "46-workflow-funding"],
      ["ethics", "47-workflow-ethics-ualberta"],
      ["participants", "48-workflow-participants"],
      ["review", "49-workflow-review"],
    ] as const) {
      await page.goto(`${b}/workflow/${slug}`);
      await expect(page.getByRole("navigation", { name: "Workflow sections" })).toBeVisible();
      await expect(page.getByRole("main").getByRole("heading").first()).toBeVisible();
      await shot(page, name);
    }

    await page.goto(`${b}/tasks?view=board`);
    await expect(
      page.getByRole("button", { name: "Fit primary RT model (FAKE)", exact: true }),
    ).toBeVisible();
    await shot(page, "50-tasks-coloured-board");
    await page.getByRole("button", { name: "Fit primary RT model (FAKE)", exact: true }).click();
    const drawer = page.getByRole("dialog");
    await drawer.getByLabel("Write an update").fill("Model fit is running; results by Friday.");
    await drawer.getByRole("button", { name: "Post update" }).click();
    const thread = drawer.getByRole("region", { name: "Updates" });
    await expect(thread.getByText("Model fit is running")).toBeVisible();
    await drawer.getByRole("button", { name: "Attach existing" }).click();
    const item = page.getByRole("menuitem").first();
    const title = ((await item.textContent()) ?? "").trim();
    await item.click();
    const files = drawer.getByRole("region", { name: "Documents and files" });
    await expect(files.getByRole("link", { name: title })).toBeVisible();
    await drawer.getByRole("button", { name: "Post update" }).scrollIntoViewIfNeeded();
    await shot(page, "51-task-drawer-thread-files");
    await files.getByRole("button", { name: `Detach ${title}` }).click();
    await thread
      .getByRole("button", { name: /^Delete/ })
      .last()
      .click();
    await thread.getByRole("button", { name: "Confirm delete post" }).click();
    await expect(thread.getByText("Model fit is running")).toHaveCount(0);

    await page.goto(`${lab(page)}/admin`);
    await expect(page.getByRole("heading", { name: "Admin", level: 1 })).toBeVisible();
    await shot(page, "52-admin");
    await page.goto(`${lab(page)}/inventory`);
    await expect(page.getByRole("heading", { name: "Inventory", level: 1 })).toBeVisible();
    await shot(page, "53-inventory");
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", level: 1 })).toBeVisible();
    await shot(page, "54-settings");
  });

  test("run 4: unread badge and dark workflow", async ({ page }) => {
    const item = (i: number) => ({
      id: `00000000-0000-0000-0000-00000000000${i}`,
      kind: "approval_expiring",
      title: `Ethics approval expires soon (${i})`,
      body: "",
      created_at: new Date().toISOString(),
      read_at: null,
    });
    await page.route(/\/notifications\/$/, (route) =>
      route.request().method() === "GET"
        ? route.fulfill({ json: [item(1), item(2), item(3)] })
        : route.continue(),
    );
    await login(page, "pi");
    await expect(page.getByRole("button", { name: "Notifications, 3 unread" })).toBeVisible();
    await shot(page, "55-unread-badge");
  });

  test("run 4: dark workflow and tasks", async ({ page }) => {
    await theme(page, "dark");
    await login(page, "pi");
    await pick(page, "Dark");
    await openProject(page);
    const b = base(page);
    await page.goto(`${b}/workflow/ethics`);
    await expect(page.getByRole("navigation", { name: "Workflow sections" })).toBeVisible();
    await shot(page, "56-dark-workflow-ethics");
    await page.goto(`${b}/tasks?view=board`);
    await expect(
      page.getByRole("button", { name: "Fit primary RT model (FAKE)", exact: true }),
    ).toBeVisible();
    await shot(page, "57-dark-tasks-board");
    await pick(page, "Light"); // leave the shared account as found
  });
});
