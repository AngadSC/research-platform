import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("an admin sees Admin and a member does not", async ({ browser }) => {
  const pi = await (await browser.newContext()).newPage();
  await login(pi, "pi");
  await expect(pi.getByRole("link", { name: "Admin", exact: true })).toBeVisible();
  await pi.getByRole("link", { name: "Admin", exact: true }).click();
  await expect(pi.getByRole("heading", { name: "Lab details" })).toBeVisible();
  await expect(pi.getByRole("heading", { name: "Institution resources" })).toBeVisible();

  const lead = await (await browser.newContext()).newPage();
  await login(lead, "lead");
  await expect(lead.getByRole("link", { name: "Inventory" })).toBeVisible();
  await expect(lead.getByRole("link", { name: "Admin", exact: true })).toHaveCount(0);
  const labPath = new URL(pi.url()).pathname.replace(/\/admin$/, "");
  await lead.goto(`${labPath}/admin`);
  await expect(lead.getByText("You don't have access to Admin")).toBeVisible();
});

test("Settings saves the theme and the default task view", async ({ page }) => {
  await login(page, "lead");
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

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
