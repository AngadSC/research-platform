import { execSync } from "node:child_process";
import { expect, test } from "@playwright/test";
import { login, loginForm, openProject, PASSWORD } from "./helpers";

test("new user signs up, confirms by emailed link, and cannot see another lab's project", async ({
  browser,
  page,
}) => {
  // The seed project's URL, as the lead sees it.
  const lead = await (await browser.newContext()).newPage();
  await login(lead, "lead");
  await openProject(lead);
  const seedUrl = lead.url().replace(/\/overview$/, "/overview");

  const email = `e2e-${Date.now()}@example.test`;
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();

  // Dev email goes to the console backend in the Celery worker (core/email.py): read the link from its log.
  let link = "";
  await expect
    .poll(
      () => {
        const log = execSync("docker compose logs worker --no-log-prefix --tail 300", {
          encoding: "utf8",
          cwd: "..",
        });
        const at = log.lastIndexOf(`To: ${email}`);
        link = (log.slice(at).match(/http:\/\/localhost:5173\/account\/verify-email\/[\w%-]+/) ?? [
          "",
        ])[0];
        return link;
      },
      { timeout: 20_000 },
    )
    .not.toBe("");
  await page.goto(link);
  await page.getByRole("button", { name: /confirm/i }).click();
  await expect(page.getByRole("heading", { name: "Email confirmed" })).toBeVisible();

  await page.context().clearCookies(); // confirming may sign the user in; start clean
  await loginForm(page, email.replace("@example.test", ""));
  await page.goto(seedUrl);
  await expect(page.getByText("We couldn't find that")).toBeVisible();
  await expect(page.getByText("Pilot Attention Study")).toHaveCount(0);
  await expect(page.getByText("Reaction time effect")).toHaveCount(0);
});

test("viewer sees no edit controls on a document or the task board", async ({ page }) => {
  // The seed gives viewer@ a viewer membership on the pilot project.
  await login(page, "viewer");
  await openProject(page);

  await page.getByRole("link", { name: "Tasks" }).click();
  await page.getByRole("button", { name: "Board" }).click();
  await expect(page.getByRole("region", { name: "To do" })).toBeVisible();
  await expect(page.getByRole("button", { name: "New task" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Move / })).toHaveCount(0);
  await expect(page.locator("[draggable=true]")).toHaveCount(0);

  await page.getByRole("link", { name: "Documents and files" }).click();
  await expect(page.getByRole("button", { name: "New document" })).toHaveCount(0);
  await page.getByText("Study protocol draft (FAKE)").click();
  await page.getByRole("button", { name: "Document options" }).click();
  await expect(page.getByText("You have read-only access.")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Save", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Title")).not.toBeEditable();
  await expect(page.getByLabel("Document content").locator("[contenteditable=true]")).toHaveCount(
    0,
  );
});
