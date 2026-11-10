import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("an admin sees the Admin group and a member does not", async ({ browser }) => {
  const pi = await (await browser.newContext()).newPage();
  await login(pi, "pi");
  await pi.getByRole("link", { name: "Lab details", exact: true }).click();
  await expect(pi.getByRole("heading", { name: "Lab details", level: 1 })).toBeVisible();
  await expect(pi.getByRole("heading", { name: "About this lab" })).toBeVisible();

  const lead = await (await browser.newContext()).newPage();
  await login(lead, "lead");
  await expect(lead.getByRole("link", { name: "Inventory" })).toBeVisible();
  await expect(lead.getByRole("navigation", { name: "Admin" })).toHaveCount(0);
  const labPath = new URL(pi.url()).pathname.replace(/\/admin$/, "");
  await lead.goto(`${labPath}/admin`);
  await expect(lead.getByText("You don't have access to Lab details")).toBeVisible();
});

test("Settings saves the theme and the default task view", async ({ page }) => {
  await login(page, "lead");
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await page.getByRole("link", { name: "Appearance" }).click();

  const appearance = page.getByRole("region", { name: "Appearance" });
  await appearance.getByRole("radio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  const tasks = page.getByRole("region", { name: "Tasks" });
  await tasks.getByRole("radio", { name: "List" }).click();
  await expect(tasks.getByRole("radio", { name: "List" })).toHaveAttribute("aria-checked", "true");

  await page.reload(); // both come back from the account, not just this browser
  await expect(
    page.getByRole("region", { name: "Tasks" }).getByRole("radio", { name: "List" }),
  ).toHaveAttribute("aria-checked", "true");
  await expect(page.locator("html")).toHaveClass(/dark/);

  // put the account back the way the other specs expect it
  await page
    .getByRole("region", { name: "Appearance" })
    .getByRole("radio", { name: "System" })
    .click();
  await page.getByRole("region", { name: "Tasks" }).getByRole("radio", { name: "Board" }).click();
  await expect(
    page.getByRole("region", { name: "Tasks" }).getByRole("radio", { name: "Board" }),
  ).toHaveAttribute("aria-checked", "true");
});
