import { expect, test, type Page } from "@playwright/test";
import { login, PROJECT } from "./helpers";

const WIDTHS = [375, 660, 800, 1024];

/** What runs past the screen. Wide tables may scroll inside their own box; the page may not. */
const measure = (page: Page) =>
  page.evaluate(() => {
    const root = document.documentElement;
    const screen = root.clientWidth;
    const main = document.querySelector("main");
    const scrollsItself = (el: Element) => {
      for (let p = el.parentElement; p && p !== main && p !== document.body; p = p.parentElement)
        if (/auto|scroll/.test(getComputedStyle(p).overflowX)) return true;
      return false;
    };
    const describe = (el: Element) =>
      `${el.tagName.toLowerCase()}.${String(el.getAttribute("class")).slice(0, 60)} "${el.textContent?.trim().slice(0, 30)}"`;
    const cutOff = Array.from(document.querySelectorAll("main *, body > div header *"))
      .filter((el) => {
        const r = el.getBoundingClientRect();
        return (
          r.width > 0 && r.right > screen + 1 && !scrollsItself(el) && !el.closest("[aria-hidden]")
        );
      })
      .slice(0, 4)
      .map(describe);
    return {
      page: root.scrollWidth - root.clientWidth,
      main: main ? main.scrollWidth - main.clientWidth : 0,
      cutOff,
    };
  });

async function check(page: Page, paths: string[], width: number) {
  await page.setViewportSize({ width, height: 800 });
  const failures: string[] = [];
  for (const path of paths) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(200);
    const m = await measure(page);
    if (m.page > 0 || m.main > 0 || m.cutOff.length)
      failures.push(`${width}px ${path}: page +${m.page}, main +${m.main} ${m.cutOff.join(" | ")}`);
  }
  expect(failures).toEqual([]);
}

test.describe("no sideways scroll", () => {
  test.setTimeout(600_000);

  const signedIn = async (page: Page) => {
    await login(page, "pi");
    const get = async <T>(url: string) => (await (await page.request.get(url)).json()) as T;
    type Row = { id: string; name?: string };
    const list = <T>(body: T[] | { results: T[] }) => ("results" in body ? body.results : body);
    const [lab] = list(await get<Row[]>("/api/labs/"));
    const L = `/labs/${lab!.id}`;
    const api = `/api/labs/${lab!.id}`;
    const project = list(await get<Row[]>(`${api}/projects/`)).find((p) => p.name === PROJECT);
    const P = `${L}/projects/${project!.id}`;
    const [doc] = list(await get<Row[]>(`${api}/projects/${project!.id}/documents/`));
    const [approval] = list(await get<Row[]>(`${api}/ethics-approvals/`));
    return [
      "/",
      "/settings",
      "/labs/new",
      `${L}/dashboard`,
      `${L}/projects`,
      `${L}/members`,
      `${L}/ethics`,
      `${L}/ethics/new`,
      ...(approval ? [`${L}/ethics/${approval.id}`] : []),
      `${L}/notifications`,
      `${L}/retention`,
      `${L}/audit-log`,
      `${L}/admin`,
      `${L}/inventory`,
      `${L}/chat`,
      `${L}/calendar`,
      `${L}/papers`,
      `${L}/training`,
      `${L}/settings/integrations`,
      `${P}/overview`,
      `${P}/handover`,
      `${P}/tasks?view=list`,
      `${P}/tasks?view=board`,
      `${P}/chat`,
      `${P}/documents`,
      ...(doc ? [`${P}/documents/${doc.id}`] : []),
      `${P}/files`,
      `${P}/lineage`,
      `${P}/workflow`,
      `${P}/workflow/funding`,
      `${P}/workflow/ethics`,
      `${P}/workflow/participants`,
      `${P}/workflow/data`,
      `${P}/workflow/analysis`,
      `${P}/workflow/manuscript`,
      `${P}/workflow/review`,
    ];
  };

  for (const width of WIDTHS) {
    test(`signed in at ${width}px`, async ({ page }) => {
      await check(page, await signedIn(page), width);
    });

    test(`signed out at ${width}px`, async ({ page }) => {
      await check(
        page,
        [
          "/",
          "/login",
          "/signup",
          "/features",
          "/workflow",
          "/for-labs",
          "/for-students",
          "/for-institutions",
          "/pricing",
        ],
        width,
      );
    });
  }
});
