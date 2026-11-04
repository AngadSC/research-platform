import { mkdirSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { login, openProject, PROJECT } from "./helpers";

const DIR = "../docs/screenshots";
mkdirSync(DIR, { recursive: true });

const shot = async (page: Page, name: string) => {
  await page.waitForLoadState("networkidle");
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
const theme = (page: Page, t: "light" | "dark") =>
  page.addInitScript((v) => localStorage.setItem("theme", v), t);
const base = (page: Page) => page.url().replace(/\/(overview|tasks|documents|files).*$/, "");
const lab = (page: Page) => page.url().match(/\/labs\/[^/]+/)![0];

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
    await page.goto(`${b}/tasks`);
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

    await page.goto(`${b}/research/datasets`);
    await expect(page.getByRole("table")).toBeVisible();
    await shot(page, "11-datasets");
    await page.goto(`${b}/research/analyses`);
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
    await expect(page.getByRole("table").getByRole("row").nth(1)).toBeVisible();
    if (!(await page.getByRole("row", { name: empty }).count())) {
      await page.getByRole("button", { name: "New project" }).first().click();
      const d = page.getByRole("dialog");
      await d.getByLabel("Name").fill(empty);
      await d.getByRole("button", { name: "Save" }).click();
      await expect(page.getByRole("row", { name: empty })).toBeVisible();
    }
    await page.getByRole("row", { name: empty }).first().click();
    await expect(page).toHaveURL(/\/overview$/);
    await page.goto(page.url().replace(/\/overview$/, "/tasks"));
    await expect(page.getByText("No tasks yet")).toBeVisible();
    await shot(page, "23-empty-state");
  });

  test("dark mode", async ({ page }) => {
    await theme(page, "dark");
    await login(page, "pi");
    await openProject(page);
    const b = base(page);
    await shot(page, "25-dark-project-overview");
    await page.goto(`${b}/lineage`);
    await expect(
      page.getByRole("button", { name: "Result: Reaction time effect (FAKE)" }),
    ).toBeVisible();
    await shot(page, "24-dark-lineage");
  });

  test("viewer read-only document", async ({ page }) => {
    await login(page, "viewer");
    await openProject(page);
    await page.goto(`${base(page)}/documents`);
    await page.getByText("Study protocol draft (FAKE)").click();
    await expect(page.getByLabel("Document content")).toBeVisible();
    await shot(page, "26-viewer-document");
  });
});
