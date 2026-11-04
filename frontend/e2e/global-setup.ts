import { chromium, expect, type FullConfig } from "@playwright/test";
import { authFile, PASSWORD, PERSONAS } from "./helpers";

/** Logs in once per persona and saves the session, so repeated runs stay under allauth's login rate limit. */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0]!.use.baseURL!;
  const browser = await chromium.launch();
  for (const who of PERSONAS) {
    const page = await (await browser.newContext({ baseURL })).newPage();
    await page.goto("/login");
    await page.getByLabel("Email").fill(`${who}@example.test`);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).not.toHaveURL(/login/);
    await page.context().storageState({ path: authFile(who) });
  }
  await browser.close();
}
