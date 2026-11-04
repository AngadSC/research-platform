import { expect, test } from "@playwright/test";
import { login, openProject, watchErrors } from "./helpers";

test("PI generates the departing student's handover", async ({ page }) => {
  await login(page, "pi");
  const errors = watchErrors(page);
  await openProject(page); // selects the lab, so the sidebar shows Members
  await page.getByRole("link", { name: "Members" }).first().click();
  await page.getByRole("link", { name: /Generate handover for student@example.test/ }).click();

  await expect(page.getByRole("heading", { name: /Handover: Sam Student/ })).toBeVisible();
  const callout = page.getByRole("region", { name: /No other owner/ });
  await expect(callout.getByText("Archived Survey (FAKE)").first()).toBeVisible();

  const analyses = page.getByRole("region", { name: /^Analyses/ });
  await expect(analyses.getByText("Primary RT model (FAKE)")).toBeVisible();
  await expect(page.getByRole("button", { name: /Print or save as PDF/ })).toBeVisible();

  expect(errors).toEqual([]);
});
