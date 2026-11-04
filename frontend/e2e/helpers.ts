import { readFileSync } from "node:fs";
import { expect, type BrowserContext, type Page } from "@playwright/test";

export const PASSWORD = "seed-password-not-secret";
export const PROJECT = "Pilot Attention Study (FAKE)";

export const PERSONAS = ["lead", "viewer", "pi"] as const;
export const authFile = (who: string) => `e2e/.auth/${who}.json`;

/** Sign in as a seed persona by loading the session saved once in global-setup (no login request). */
export async function login(page: Page, who: string) {
  const state = JSON.parse(readFileSync(authFile(who), "utf8")) as {
    cookies: Parameters<BrowserContext["addCookies"]>[0];
  };
  await page.context().addCookies(state.cookies);
  await page.goto("/");
  await expect(page).not.toHaveURL(/login/);
}

/** Sign in through the form (for users created during a test). */
export async function loginForm(page: Page, who: string) {
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
