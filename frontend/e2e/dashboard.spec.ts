import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("Home shows the PI the lab and a member their own tasks", async ({ browser }) => {
  const pi = await (await browser.newContext()).newPage();
  await login(pi, "pi");
  await expect(pi).toHaveURL(/\/labs\/[^/]+\/dashboard$/);
  await expect(pi.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();
  await expect(pi.getByRole("heading", { name: "People" })).toBeVisible();

  const member = await (await browser.newContext()).newPage();
  await login(member, "lead");
  await expect(member.getByRole("heading", { name: "My tasks" })).toBeVisible();
  await expect(member.getByRole("heading", { name: "People" })).toHaveCount(0);
});
