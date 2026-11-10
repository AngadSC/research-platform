import { expect, test } from "@playwright/test";
import { login, openProject, watchErrors } from "./helpers";

const TABS = ["Funding", "Ethics", "Participants", "Data", "Analysis", "Manuscript", "Review"];

test("Workflow sub-tabs, record pages and the old Research addresses", async ({ page }) => {
  await login(page, "lead");
  const errors = watchErrors(page);
  await openProject(page);
  const project = page.url().replace(/\/overview$/, "");

  // The project tabs: Workflow replaces Research, and opens on the first stage not done.
  await expect(page.getByRole("link", { name: "Research" })).toHaveCount(0);
  await page.getByRole("link", { name: "Workflow" }).click();
  await expect(page).toHaveURL(/\/workflow\/[a-z]+$/);

  // Stages in the agreed order, with Lineage as a view beside them.
  const nav = page.getByRole("navigation", { name: "Workflow sections" });
  await expect(nav.getByRole("link")).toHaveText(TABS);
  await expect(page.getByRole("link", { name: "Lineage" })).toBeVisible();

  // Participants always carries the no-personal-data warning.
  await nav.getByRole("link", { name: "Participants" }).click();
  await expect(page.getByRole("note")).toContainText("Don't enter names or identifying details");

  // Data lists datasets; opening one shows breadcrumbs through Workflow.
  await nav.getByRole("link", { name: "Data" }).click();
  await page.getByRole("row").nth(1).click();
  const crumbs = page.getByRole("navigation", { name: /breadcrumb/i });
  await expect(crumbs).toContainText("Workflow");
  await expect(crumbs).toContainText("Data");

  // Decisions live under Review.
  await nav.getByRole("link", { name: "Review" }).click();
  await expect(page.getByRole("heading", { name: "Decisions" })).toBeVisible();

  // Old Research links still land in the right place.
  await page.goto(`${project}/research/analyses`);
  await expect(page).toHaveURL(/\/workflow\/analysis$/);
  await page.goto(`${project}/research`);
  await expect(page).toHaveURL(/\/workflow\/data$/);

  expect(errors).toEqual([]);
});
