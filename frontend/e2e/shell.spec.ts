import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("marketing home has Sign in at the top right, leading to the sign-in page", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Run your entire lab on one platform." }),
  ).toBeVisible();
  const signIn = page.getByRole("banner").getByRole("link", { name: "Sign in" });
  await expect(signIn).toBeVisible();
  await expect(page.getByRole("banner").getByRole("link", { name: "Contact us" })).toBeVisible();
  const box = (await signIn.boundingBox())!;
  expect(box.x).toBeGreaterThan(page.viewportSize()!.width / 2);
  expect(box.y).toBeLessThan(140);
  await signIn.click();
  await expect(page).toHaveURL(/\/login/);
});

test("dark mode persists across a reload and is saved to the account", async ({ page }) => {
  await login(page, "pi");
  const html = page.locator("html");
  const saved = page.waitForResponse(
    (r) => r.url().includes("/api/me/") && r.request().method() === "PATCH",
  );
  await page.getByRole("radio", { name: "Dark" }).click();
  await saved;
  await expect(html).toHaveClass(/dark/);
  await page.reload();
  await expect(html).toHaveClass(/dark/);
  const back = page.waitForResponse(
    (r) => r.url().includes("/api/me/") && r.request().method() === "PATCH",
  );
  await page.getByRole("radio", { name: "Light" }).click();
  await back;
  await expect(html).not.toHaveClass(/dark/);
});

test("Ctrl+F opens search, but not inside a text field", async ({ page }) => {
  await login(page, "pi");
  await page.getByRole("heading", { name: "Projects", exact: true }).click(); // focus off the text field
  await page.keyboard.press("Control+f");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.locator("#app-sidebar").getByRole("link", { name: "Admin" }).click(); // the PI lands on the Dashboard, which has no text field
  await page.getByLabel("Lab name").focus();
  await page.keyboard.press("Control+f");
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("unread badge shows the count on the sidebar and the bell", async ({ page }) => {
  const item = (i: number) => ({
    id: `00000000-0000-0000-0000-00000000000${i}`,
    kind: "approval_expiring",
    title: `Test notification ${i}`,
    body: "",
    created_at: new Date().toISOString(),
    read_at: null,
  });
  await page.route(/\/notifications\/$/, (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ json: [item(1), item(2), item(3)] })
      : route.continue(),
  );
  await login(page, "pi");
  const nav = page.locator("#app-sidebar");
  await expect(nav.getByLabel("3 unread notifications").first()).toHaveText("3");
  await expect(page.getByRole("button", { name: "Notifications, 3 unread" })).toBeVisible();
});
