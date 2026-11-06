import { expect, test, type Page } from "@playwright/test";
import { login, PROJECT, watchErrors } from "./helpers";

test.use({ viewport: { width: 390, height: 844 } });

test.beforeEach(async ({ page }) => {
  await login(page, "lead");
});

/** The project list lives in the drawer below md, so open it first. */
async function openProject(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.locator("#app-sidebar").getByRole("link", { name: PROJECT }).click();
  await expect(page).toHaveURL(/\/overview$/);
}

test("sidebar is a drawer below md: hidden until the toggle opens it", async ({ page }) => {
  const errors = watchErrors(page);
  await openProject(page);
  const sidebar = page.locator("#app-sidebar");
  const toggle = page.getByRole("button", { name: "Open navigation" });
  await expect(sidebar).toBeHidden();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");

  await toggle.click();
  await expect(sidebar).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(errors).toEqual([]);
});

test("Escape and a backdrop click close the drawer", async ({ page }) => {
  await openProject(page);
  const sidebar = page.locator("#app-sidebar");
  const toggle = page.getByRole("button", { name: "Open navigation" });

  await toggle.click();
  await page.keyboard.press("Escape");
  await expect(sidebar).toBeHidden();

  await toggle.click();
  await page.mouse.click(370, 600); // over the backdrop, right of the drawer
  await expect(sidebar).toBeHidden();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
});

test("navigating from the drawer closes it", async ({ page }) => {
  await openProject(page);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.locator("#app-sidebar").getByRole("link", { name: "Settings" }).click();
  await expect(page).toHaveURL(/\/settings/);
  await expect(page.locator("#app-sidebar")).toBeHidden();
});

test("projects page has no horizontal overflow", async ({ page }) => {
  await openProject(page);
  const lab = new URL(page.url()).pathname.split("/")[2];
  await page.goto(`/labs/${lab}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBe(0);
});
