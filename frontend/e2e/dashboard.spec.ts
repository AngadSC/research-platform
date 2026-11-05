import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("the PI lands on the dashboard and a member does not see it", async ({ browser }) => {
  const pi = await (await browser.newContext()).newPage();
  await login(pi, "pi");
  await expect(pi).toHaveURL(/\/labs\/[^/]+\/dashboard$/);
  await expect(pi.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(pi.getByRole("region", { name: "Summary" })).toBeVisible();
  await expect(pi.getByRole("link", { name: "Dashboard" })).toBeVisible();

  const member = await (await browser.newContext()).newPage();
  await login(member, "lead");
  await expect(member).not.toHaveURL(/dashboard/);
  await expect(member.getByRole("link", { name: "Dashboard" })).toHaveCount(0);
  await member.goto(pi.url());
  await expect(member.getByText("The dashboard is for PIs and lab admins")).toBeVisible();
});
