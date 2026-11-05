import { expect, test } from "@playwright/test";
import { login, openProject, watchErrors } from "./helpers";

const COMMIT = /\b3f2c9a1e7b4d0{28}\b/;

test("trace a result and a manuscript back to dataset version and commit in two clicks", async ({
  page,
}) => {
  await login(page, "lead"); // the pre-login session probe is an expected 401
  const errors = watchErrors(page);
  await openProject(page);

  // Click 1: Lineage tab. Click 2: the result.
  await page.getByRole("link", { name: "Lineage" }).click();
  await page.getByRole("button", { name: "Result: Reaction time effect (FAKE)" }).click();
  const panel = page.getByRole("dialog");
  await expect(panel.getByText("v2", { exact: true })).toBeVisible();
  await expect(panel.getByText(COMMIT)).toBeVisible();

  // Manuscript: result, commit and dataset version in the same single panel.
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await page
    .getByRole("button", { name: "Manuscript: Attention and response speed (draft, FAKE)" })
    .click();
  await expect(panel.getByText("Reaction time effect (FAKE)").first()).toBeVisible();
  await expect(panel.getByText(COMMIT)).toBeVisible();
  await expect(panel.getByText("v2", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");

  // List view shows the same chain.
  await page.getByRole("button", { name: "List view" }).click();
  const list = page.getByTestId("lineage-list");
  const result = list.getByRole("listitem").filter({ hasText: "Reaction time effect (FAKE)" });
  await expect(result.first()).toContainText("Primary RT model (FAKE)");
  await expect(result.first()).toContainText("3f2c9a1e7b4d");
  await expect(result.first()).toContainText("v2");

  expect(errors).toEqual([]);
});

test("?focus opens the item's panel", async ({ page }) => {
  await login(page, "lead");
  await openProject(page);
  await page.getByRole("link", { name: "Workflow" }).click();
  await page.getByRole("link", { name: "Analysis", exact: true }).click();
  await page.getByText("Reaction time effect (FAKE)").click();
  await expect(page.getByRole("navigation", { name: /breadcrumb/i })).toContainText(
    "Reaction time effect (FAKE)",
  );
  await page.getByRole("link", { name: "View in lineage" }).click();
  await expect(page.getByRole("dialog")).toContainText("Reaction time effect (FAKE)");
});
