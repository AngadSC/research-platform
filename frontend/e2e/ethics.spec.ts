import { execSync } from "node:child_process";
import { expect, test } from "@playwright/test";
import { login, openProject, PROJECT } from "./helpers";

// Reminders come from a daily job; run it now (it is idempotent, so reruns create nothing new).
test.beforeAll(() => {
  execSync(
    `docker compose run --rm backend sh -c "python manage.py shell -c 'from ethics.jobs import send_expiry_reminders; send_expiry_reminders()'"`,
    { cwd: "..", stdio: "pipe" },
  );
});

test("PI sees the seed approval expiring, its reminder in the bell, and the retention review", async ({
  page,
}) => {
  await login(page, "pi");
  await openProject(page);

  // The sidebar no longer lists ethics; the lab-wide list is one link away in Workflow > Ethics.
  await page.getByRole("link", { name: "Workflow" }).click();
  await page.getByRole("link", { name: "Ethics", exact: true }).click();
  await page.getByRole("link", { name: "See every approval in the lab" }).click();
  const row = page.getByRole("row", { name: /FAKE-IRB-2026-001/ });
  await expect(row).toContainText(/in \d+ days/);
  await expect(row.getByText("active", { exact: true })).toHaveClass(/text-warning/);

  await row.click();
  await expect(
    page.getByRole("heading", { name: "Pilot attention study approval (FAKE)" }),
  ).toBeVisible();
  // The project overview lists the same approval.
  await page.getByRole("main").getByRole("link", { name: PROJECT }).click();
  await expect(page.getByRole("main")).toContainText("FAKE-IRB-2026-001");

  await page.getByRole("button", { name: /^Notifications, \d+ unread$/ }).click();
  await expect(page.getByRole("menu")).toContainText(/FAKE-IRB-2026-001 expires in \d+ day/);
  await page.keyboard.press("Escape");

  await page.getByRole("link", { name: "Retention review" }).click();
  await expect(
    page.getByText("Nothing is deleted automatically. Review each item and decide what to keep."),
  ).toBeVisible();
  await expect(
    page.getByRole("table").getByRole("link", { name: "Archived Survey (FAKE)" }),
  ).toBeVisible();
});
