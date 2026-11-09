import { expect, test, type Page } from "@playwright/test";
import { login, openProject } from "./helpers";

async function openDoc(page: Page, title: string) {
  await openProject(page);
  await page.getByRole("link", { name: "Documents" }).click();
  await page.getByText(title).click();
  await expect(page.getByLabel("Document content")).toBeVisible();
}

const editor = (page: Page) =>
  page.getByLabel("Document content").locator("[contenteditable=true]");

test("editor renders, saves with Ctrl+S, revisions preview and restore", async ({ page }) => {
  await login(page, "lead");
  await openDoc(page, "Study protocol draft (FAKE)");
  await expect(editor(page)).toBeEditable();

  const marker = `E2E edit ${Date.now()}`;
  await editor(page).click();
  await page.keyboard.press("Control+End");
  await page.keyboard.type(marker);
  await page.keyboard.press("Control+s");
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  await expect(editor(page)).toContainText(marker);

  // Revision 1 is the original text; preview it, then restore it.
  await page.getByRole("button", { name: "Document options" }).click();
  await page.getByRole("menuitem", { name: "History" }).click();
  await page.getByRole("button", { name: /^Version 1\b/ }).click();
  const preview = page.getByLabel("Version 1 preview");
  await expect(preview).toContainText("Fake placeholder text for a dev database.");
  await expect(preview).not.toContainText(marker);
  await page.getByRole("button", { name: "Restore this version" }).click();
  await page.getByRole("button", { name: "Restore", exact: true }).click();
  await expect(page.getByText(/Restored as version/)).toBeVisible();
  await expect(editor(page)).toContainText("Fake placeholder text for a dev database.");
  await expect(editor(page)).not.toContainText(marker);
});

test("a document autosaves and a folder takes it", async ({ page }) => {
  await login(page, "lead");
  await openDoc(page, "Meeting notes (FAKE)");
  const marker = `autosaved ${Date.now()}`;
  await editor(page).click();
  await page.keyboard.press("Control+End");
  await page.keyboard.type(marker);
  await expect(page.getByText("Saved", { exact: true })).toBeVisible({ timeout: 8000 });
  await page.reload();
  await expect(editor(page)).toContainText(marker);

  const folderName = `Folder ${Date.now()}`;
  await page.getByRole("link", { name: "Documents" }).click();
  await page.getByRole("button", { name: "New folder" }).click();
  await page.getByLabel("Name").fill(folderName);
  await page.getByRole("button", { name: "Save" }).click();
  await page.getByRole("button", { name: "Actions for Meeting notes (FAKE)" }).click();
  await page.getByRole("menuitem", { name: "Move to folder" }).click();
  await page.getByLabel("Folder").selectOption({ label: folderName });
  await page.getByRole("button", { name: "Move", exact: true }).click();
  await expect(page.getByText("Meeting notes (FAKE)")).toBeHidden();
  await page.getByRole("link", { name: folderName }).click();
  await expect(page.getByText("Meeting notes (FAKE)")).toBeVisible();
  // Deleting the folder hands the document back to the top level.
  await page.getByRole("link", { name: "All" }).click();
  await page.getByRole("button", { name: `Actions for ${folderName}` }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await page.getByRole("button", { name: "Delete folder" }).click();
  await expect(page.getByText("Meeting notes (FAKE)")).toBeVisible();
});

test("saving from a stale copy shows the conflict dialog", async ({ browser }) => {
  const a = await (await browser.newContext()).newPage();
  const b = await (await browser.newContext()).newPage();
  await login(a, "lead");
  await login(b, "lead");
  await openDoc(a, "Meeting notes (FAKE)");
  await openDoc(b, "Meeting notes (FAKE)");

  for (const [page, text] of [
    [a, " first"],
    [b, " second"],
  ] as const) {
    await editor(page).click();
    await page.keyboard.press("Control+End");
    await page.keyboard.type(text);
    await page.keyboard.press("Control+s");
  }
  await expect(a.getByText("Saved", { exact: true })).toBeVisible();
  await expect(b.getByText("This document changed since you opened it")).toBeVisible();
});
