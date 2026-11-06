import { expect, test } from "@playwright/test";
import { login, openProject, projectUrl } from "./helpers";

test("open a task, post an update, attach a document", async ({ page }) => {
  await login(page, "lead");
  await openProject(page);
  await page.goto(`${projectUrl(page)}/tasks?view=board`);

  await page.getByRole("button", { name: "Fit primary RT model (FAKE)", exact: true }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByLabel("Title")).toHaveValue("Fit primary RT model (FAKE)");

  // Post an update; it shows with its author, and markdown is rendered.
  const text = `E2E update ${Date.now()}`;
  await drawer.getByLabel("Write an update").fill(`**${text}**`);
  await drawer.getByRole("button", { name: "Post update" }).click();
  const thread = drawer.getByRole("region", { name: "Updates" });
  await expect(thread.locator("strong", { hasText: text })).toBeVisible();

  // Attach an existing document, see it listed, then detach it so the test can run again.
  await drawer.getByRole("button", { name: "Attach existing" }).click();
  const item = page.getByRole("menuitem").first();
  const title = ((await item.textContent()) ?? "").trim();
  await item.click();
  const files = drawer.getByRole("region", { name: "Documents and files" });
  await expect(files.getByRole("link", { name: title })).toBeVisible();
  await files.getByRole("button", { name: `Detach ${title}` }).click();
  await expect(files.getByRole("link", { name: title })).toHaveCount(0);

  // The author deletes their own post.
  await thread
    .getByRole("button", { name: /^Delete/ })
    .last()
    .click();
  await thread.getByRole("button", { name: "Confirm delete post" }).click();
  await expect(thread.locator("strong", { hasText: text })).toHaveCount(0);
});
