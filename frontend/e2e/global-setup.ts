import { chromium, expect, type FullConfig } from "@playwright/test";
import { authFile, PASSWORD, PERSONAS } from "./helpers";

/** Logs in once per persona and saves the session, so repeated runs stay under allauth's login rate limit. */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0]!.use.baseURL!;
  const browser = await chromium.launch();
  for (const who of PERSONAS) {
    const page = await (await browser.newContext({ baseURL })).newPage();
    // The app fetches its CSRF token on load; signing in before that gives a 403.
    const config = page.waitForResponse((r) => r.url().includes("/_allauth/browser/v1/config"));
    await page.goto("/login");
    await config;
    await page.getByLabel("Email").fill(`${who}@example.test`);
    await page.getByRole("button", { name: "Continue" }).click(); // email step (D156)
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).not.toHaveURL(/login/, { timeout: 20_000 });
    // Signed-in shell rendered: the session cookie is settled before it is saved.
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({ timeout: 20_000 });
    await page.context().storageState({ path: authFile(who) });
  }
  await browser.close();
}
