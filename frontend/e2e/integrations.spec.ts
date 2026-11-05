import { expect, test } from "@playwright/test";
import { login, openProject } from "./helpers";

test("Integrations page groups providers by category", async ({ page }) => {
  await login(page, "lead");
  await openProject(page);
  const lab = page.url().match(/\/labs\/[^/]+/)![0];
  await page.goto(`${lab}/settings/integrations`);
  await expect(page.getByRole("heading", { name: "Integrations", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "File storage" })).toBeVisible();
  await expect(page.getByText("Google Drive").first()).toBeVisible();
});

// Overleaf is the link-only provider (no API), and it links to manuscripts.
test("paste an Overleaf link onto a manuscript with a title, then remove it", async ({ page }) => {
  await login(page, "lead");
  await openProject(page);
  const base = page.url().replace(/\/(overview|tasks|documents|files).*$/, "");
  await page.goto(`${base}/research/manuscripts`);
  await page.getByRole("row").nth(1).click();

  const title = `e2e Overleaf ${Date.now()}`;
  await page.getByRole("button", { name: /Link from/ }).click();
  await page.getByRole("menuitem", { name: /Overleaf/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Overleaf link").fill("https://example.com/not-overleaf");
  await dialog.getByLabel("Title").fill(title);
  await dialog.getByRole("button", { name: "Link", exact: true }).click();
  await expect(dialog.getByText(/does not look like a Overleaf link/)).toBeVisible();

  await dialog
    .getByLabel("Overleaf link")
    .fill("https://www.overleaf.com/project/0123456789abcdef01234567");
  await dialog.getByRole("button", { name: "Link", exact: true }).click();
  await expect(page.getByRole("link", { name: new RegExp(title) })).toBeVisible();
  await expect(page.getByText(/Overleaf's own sharing settings/).first()).toBeVisible();

  await page.getByRole("button", { name: `Remove link to ${title}` }).click();
  await expect(page.getByRole("link", { name: new RegExp(title) })).toBeHidden();
});
