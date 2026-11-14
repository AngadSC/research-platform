import { expect, test } from "@playwright/test";
import { login, openProject, watchErrors } from "./helpers";

test("chat composer: format, emoji, @mention, and the mentioned person is told", async ({
  page,
  browser,
}) => {
  const errors = watchErrors(page);
  await login(page, "lead");
  await openProject(page);
  await page.getByRole("button", { name: /^Chat/ }).click();

  await expect(page.getByRole("toolbar", { name: "Formatting" })).toBeVisible();
  const box = page.getByRole("textbox", { name: "Message" });
  const stamp = Date.now();
  await box.fill(`bold test ${stamp}`);
  await box.selectText();
  await page.getByRole("button", { name: "Bold", exact: true }).click();
  await expect(box).toHaveValue(`**bold test ${stamp}**`);

  await box.press(process.platform === "darwin" ? "Meta+ArrowDown" : "Control+End"); // to the end
  await page.getByRole("button", { name: "Emoji", exact: true }).click();
  await page.getByLabel("Search emoji").fill("rocket");
  await page.getByRole("button", { name: /rocket/ }).click();
  await expect(box).toHaveValue(/\*\*🚀$/);

  await page.getByRole("button", { name: "Mention someone", exact: true }).click();
  const options = page.getByRole("option");
  await expect(options.first()).toBeVisible();
  await options.first().click();
  await expect(box).toHaveValue(/@\S[^(]* $/); // the name, never the stored code
  await expect(box).not.toHaveValue(/user:/);
  await page.screenshot({ path: "test-results/composer-desktop.png" });
  await box.press("Enter");
  await expect(box).toHaveValue("");

  const log = page.getByRole("log", { name: "Messages" });
  await expect(log.locator("strong", { hasText: `bold test ${stamp}` })).toBeVisible();
  await expect(log.getByText(/^@\S/).last()).toBeVisible(); // a chip, not the raw token
  await expect(log).not.toContainText("(user:");

  // Hiding the formatting row is remembered.
  await page.getByRole("button", { name: "Formatting", exact: true }).click();
  await expect(page.getByRole("toolbar")).toHaveCount(0);
  await page.reload(); // the chat panel reopens from ?chat=1
  await expect(box).toBeVisible();
  await expect(page.getByRole("toolbar")).toHaveCount(0);
  await page.getByRole("button", { name: "Formatting", exact: true }).click();

  expect(errors.filter((e) => !/favicon|401|403/.test(e))).toEqual([]);

  // A phone-sized screen keeps the whole composer on screen.
  await page.setViewportSize({ width: 375, height: 700 });
  await page.screenshot({ path: "test-results/composer-375.png" });
  const bar = await page.getByRole("toolbar").boundingBox();
  expect(bar!.x + bar!.width).toBeLessThanOrEqual(375);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  void browser;
});

test("documents: @ lists project members and ':' offers emoji", async ({ page }) => {
  await login(page, "lead");
  await openProject(page);
  await page.getByRole("link", { name: "Documents and files" }).click();
  await page.getByText("Study protocol draft (FAKE)").click();
  const editor = page.getByLabel("Document content").locator("[contenteditable=true]");
  await expect(editor).toBeEditable();
  await editor.click();
  await page.keyboard.press("Control+End");
  await page.keyboard.type(" @");
  const item = page.locator(".bn-suggestion-menu-item").first();
  await expect(item).toBeVisible();
  const name = (await item.innerText()).trim().split("\n")[0]!;
  await page.keyboard.press("Enter");
  await expect(editor).toContainText(`@${name}`);
  await page.keyboard.type(" :rocket");
  await expect(page.locator(".bn-grid-suggestion-menu, .bn-suggestion-menu").first()).toBeVisible();
  await page.screenshot({ path: "test-results/composer-doc.png" });
});
