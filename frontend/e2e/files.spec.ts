import { expect, test } from "@playwright/test";
import { login, openProject } from "./helpers";

/** A valid n-page PDF with a correct xref table. */
function pdf(pages: number): Buffer {
  const kids = Array.from({ length: pages }, (_, i) => `${i + 3} 0 R`).join(" ");
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    `<< /Type /Pages /Kids [${kids}] /Count ${pages} >>`,
    ...Array.from(
      { length: pages },
      () => "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
    ),
  ];
  let body = "%PDF-1.4\n";
  const offsets = objs.map((o, i) => {
    const at = body.length;
    body += `${i + 1} 0 obj\n${o}\nendobj\n`;
    return at;
  });
  const xref = body.length;
  body += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`;
  body += offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  body += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(body, "latin1");
}

test("upload a PDF behind the notice, then view it and turn pages", async ({ page }) => {
  await login(page, "lead");
  await openProject(page);
  await page.getByRole("link", { name: "Files" }).click();
  await page.getByRole("button", { name: "Upload file" }).first().click();

  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByText(
      "Do not upload participant identifiers. Upload only anonymized or aggregate data.",
    ),
  ).toBeVisible();
  const name = `e2e-${Date.now()}.pdf`;
  await dialog.getByLabel("Choose file").setInputFiles({
    name,
    mimeType: "application/pdf",
    buffer: pdf(2),
  });
  const upload = dialog.getByRole("button", { name: "Upload", exact: true });
  await expect(upload).toBeDisabled();
  await dialog.getByRole("checkbox").check();
  await expect(upload).toBeEnabled();
  await upload.click();
  await expect(page.getByText("File uploaded")).toBeVisible();

  await page.getByRole("link", { name: `Open ${name}` }).click();
  const canvas = page.locator("canvas");
  await expect(canvas).toBeVisible();
  await expect
    .poll(() => canvas.evaluate((c: HTMLCanvasElement) => c.width * c.height))
    .toBeGreaterThan(1000);
  await expect(page.getByText("Page 1 of 2")).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Page 2 of 2")).toBeVisible();
  await page.getByRole("button", { name: "Previous" }).click();
  await expect(page.getByText("Page 1 of 2")).toBeVisible();
});
