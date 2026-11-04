import { expect, type Page } from "@playwright/test";

export const PASSWORD = "seed-password-not-secret";
export const PROJECT = "Pilot Attention Study (FAKE)";

export async function login(page: Page, who: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(`${who}@example.test`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/login/);
}

/** From the home page, open the seed project's overview. */
export async function openProject(page: Page) {
  await page.goto("/");
  await page.getByRole("link", { name: PROJECT }).first().click();
  await expect(page).toHaveURL(/\/overview$/);
}

/** Collect console errors and uncaught page errors. */
export function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  return errors;
}

export const projectUrl = (page: Page) => page.url().replace(/\/overview$/, "");
