import { expect, test } from "@playwright/test";
import { login, openProject, watchErrors } from "./helpers";

test("two project members talk: a message reaches the other person without a reload", async ({
  page,
  browser,
}) => {
  const errors = watchErrors(page);
  await login(page, "lead");
  await openProject(page);
  const sidebar = page.locator("#app-sidebar");
  await expect(sidebar.getByRole("link", { name: "Overview" })).toBeVisible();
  await page.getByRole("button", { name: /^Chat/ }).click();
  await expect(page).toHaveURL(/[?&]chat=1$/);

  const other = await (await browser.newContext()).newPage();
  await login(other, "viewer"); // viewers can post too (D206)
  await openProject(other);
  await other.getByRole("button", { name: /^Chat/ }).click();

  const text = `Hello from the viewer ${Date.now()} (FAKE)`;
  const box = other.getByRole("textbox", { name: "Message" });
  await box.fill(text);
  await box.press("Enter");
  await expect(box).toHaveValue("");

  const log = page.getByRole("log", { name: "Messages" });
  await expect(log.getByText(text)).toBeVisible({ timeout: 10_000 }); // arrives by polling

  await log.getByText(text).hover();
  await page.getByRole("button", { name: `Delete message: ${text.slice(0, 40)}` }).click();
  await page.getByRole("button", { name: "Delete message", exact: true }).click();
  await expect(log.getByText(text)).toHaveCount(0);
  await expect(other.getByRole("log").getByText(text)).toHaveCount(0, { timeout: 10_000 });
  expect(errors).toEqual([]);
});

test("a badge shows unread messages until the chat is opened", async ({ page, browser }) => {
  await login(page, "lead");
  await openProject(page); // on Overview, so the Chat row is in view but not open
  // The open panel hides the page behind it from the accessibility tree, badge included.
  const chatLink = page.getByRole("button", { name: /^Chat/, includeHidden: true });

  const other = await (await browser.newContext()).newPage();
  await login(other, "viewer");
  await openProject(other);
  await other.getByRole("button", { name: /^Chat/ }).click();
  const box = other.getByRole("textbox", { name: "Message" });
  await box.fill(`Unread test ${Date.now()} (FAKE)`);
  await box.press("Enter");
  await expect(box).toHaveValue("");

  const badge = chatLink.getByRole("img", { name: /unread message/, includeHidden: true });
  await expect(badge).toBeVisible({ timeout: 20_000 }); // badge polls
  await chatLink.click();
  await expect(badge).toHaveCount(0);
  await page.reload(); // cleared on the server, not just on this screen
  await expect(page.getByRole("log", { name: "Messages" })).toBeVisible();
  await expect(badge).toHaveCount(0);
});

test("messages stay unread while you are scrolled up, until you come back down", async ({
  page,
  browser,
}) => {
  const other = await (await browser.newContext()).newPage();
  await login(other, "viewer");
  await openProject(other);
  await other.getByRole("button", { name: /^Chat/ }).click();
  const box = other.getByRole("textbox", { name: "Message" });
  const post = async (text: string) => {
    await box.fill(text);
    await box.press("Enter");
    await expect(box).toHaveValue("");
  };
  const run = Date.now(); // the dev database keeps earlier runs' messages
  for (let i = 0; i < 25; i++) await post(`Scroll filler ${i} ${run} (FAKE)`); // enough to scroll

  await login(page, "pi");
  await openProject(page);
  // The open panel hides the page behind it from the accessibility tree, badge included.
  const chatLink = page.getByRole("button", { name: /^Chat/, includeHidden: true });
  await chatLink.click();
  const log = page.getByRole("log", { name: "Messages" });
  await expect(log.getByText(`Scroll filler 24 ${run} (FAKE)`)).toBeVisible();
  const badge = chatLink.getByRole("img", { name: /unread message/, includeHidden: true });
  await expect(badge).toHaveCount(0);

  await log.hover();
  await page.mouse.wheel(0, -1000);
  await expect(log.getByText(`Scroll filler 24 ${run} (FAKE)`)).not.toBeInViewport();

  await post(`While scrolled up ${Date.now()} (FAKE)`);
  const jump = page.getByRole("button", { name: "New messages" });
  await expect(jump).toBeVisible({ timeout: 10_000 });
  await expect(
    chatLink.getByRole("img", { name: "1 unread message", includeHidden: true }),
  ).toBeAttached({ timeout: 20_000 });

  await jump.click();
  await expect(badge).toHaveCount(0);
});
