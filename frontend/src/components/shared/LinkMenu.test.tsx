import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { checkPastedUrl } from "@/lib/integrations";
import { connected, KEYED, LINK_ONLY, OAUTH, PUBLIC } from "@/test/providers";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

vi.mock("pdfjs-dist", () => ({ GlobalWorkerOptions: {}, getDocument: vi.fn() }));

const project = {
  id: "p1",
  name: "Gut study",
  description: "",
  status: "active",
  start_date: null,
  retain_until: null,
  retention_note: "",
  created_by: { id: "u1", email: "ada@uni.edu", display_name: "Ada" },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  my_project_role: "lead",
  my_permissions: ["view_project", "edit_content"],
};
const FILES = "/labs/lab1/projects/p1/files";
const LINKS = "/api/labs/lab1/projects/p1/external-links/";
const SEARCH = "/api/labs/lab1/projects/p1/integrations/dropbox/search/";
const made = { id: "l1", title: "Linked thing", version_note: "none" };
const setup = (providers: unknown[], extra: Record<string, object> = {}) =>
  mockFetch({
    [SESSION]: signedIn,
    "GET /api/labs/": { body: [makeLab(["view_lab"])] },
    "GET /api/labs/lab1/projects/": { body: [project] },
    "GET /api/labs/lab1/projects/p1/": { body: project },
    "GET /api/labs/lab1/projects/p1/attachments/": { body: [] },
    "GET /api/labs/lab1/integrations/providers/": { body: providers },
    [`GET ${LINKS}`]: { body: [] },
    ...extra,
  });
const openMenu = async () =>
  userEvent.click(await screen.findByRole("button", { name: /Link from/ }));
const result = {
  id: "f1",
  title: "Raw data",
  subtitle: "/lab/raw",
  modified: "2026-01-01T00:00:00Z",
};

afterEach(() => vi.unstubAllGlobals());

describe("Link from menu", () => {
  it("lists only usable providers for the target kind", async () => {
    // OAuth not connected: out. Keyed connected: in. Link-only: always in. Public offers
    // dataset and result only, not the project: out.
    setup([OAUTH, connected(KEYED), LINK_ONLY, PUBLIC]);
    renderRoute(FILES);
    await openMenu();
    expect(await screen.findByRole("menuitem", { name: /Zotero/ })).toBeVisible();
    expect(screen.getByRole("menuitem", { name: /Overleaf/ })).toBeVisible();
    expect(screen.queryByRole("menuitem", { name: /Dropbox/ })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: /Zenodo/ })).toBeNull();
  });

  it("is absent when no provider offers the target", async () => {
    setup([PUBLIC]);
    renderRoute(FILES);
    await screen.findByText("No files yet");
    expect(screen.queryByRole("button", { name: /Link from/ })).toBeNull();
  });

  it("searches after a pause and cancels the stale request", async () => {
    const signals: Record<string, AbortSignal | null | undefined> = {};
    setup([connected(OAUTH)]);
    const inner = globalThis.fetch;
    vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => {
      const u = String(input);
      if (!u.startsWith(SEARCH)) return inner(input, init);
      signals[u] = init?.signal;
      // The "ab" request never answers, so only an abort can end it.
      return u.includes("q=ab&")
        ? new Promise<Response>(() => {})
        : Promise.resolve(new Response(JSON.stringify([result]), { status: 200 }));
    });
    renderRoute(FILES);
    await openMenu();
    await userEvent.click(await screen.findByRole("menuitem", { name: /Dropbox/ }));
    await screen.findByText("Raw data"); // the empty query shows recent items
    expect(Object.keys(signals)).toEqual([`${SEARCH}?q=&target=project`]);
    const box = screen.getByRole("searchbox");
    await userEvent.type(box, "ab");
    await waitFor(() => expect(signals[`${SEARCH}?q=ab&target=project`]).toBeTruthy());
    await userEvent.type(box, "c");
    await waitFor(() => expect(signals[`${SEARCH}?q=abc&target=project`]).toBeTruthy());
    expect(signals[`${SEARCH}?q=ab&target=project`]?.aborted).toBe(true);
    expect(`${SEARCH}?q=a&target=project` in signals).toBe(false); // no request per keystroke
    expect(await screen.findByText(/\/lab\/raw/)).toBeVisible();
    expect(screen.getByText(/Modified/)).toBeVisible();
  });

  it("links a search result by id only", async () => {
    const calls = setup([connected(OAUTH)], {
      [`GET ${SEARCH}?q=&target=project`]: { body: [result] },
      [`POST ${LINKS}`]: { status: 201, body: made },
    });
    renderRoute(FILES);
    await openMenu();
    await userEvent.click(await screen.findByRole("menuitem", { name: /Dropbox/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Raw data/ }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        provider: "dropbox",
        external_id: "f1",
      }),
    );
  });

  it("validates a pasted URL against url_pattern, then links a link-only item with its title", async () => {
    const calls = setup([LINK_ONLY], { [`POST ${LINKS}`]: { status: 201, body: made } });
    renderRoute(FILES);
    await openMenu();
    await userEvent.click(await screen.findByRole("menuitem", { name: /Overleaf/ }));
    const url = await screen.findByLabelText("Overleaf link");
    await userEvent.type(url, "https://example.com/project/abc");
    await userEvent.click(screen.getByRole("button", { name: "Link" }));
    expect(await screen.findByText(/does not look like a Overleaf link/)).toBeVisible();
    expect(screen.getByText("Enter a title for this link.")).toBeVisible();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await userEvent.clear(url);
    await userEvent.type(url, "https://www.overleaf.com/project/0123456789abcdef01234567");
    await userEvent.type(screen.getByLabelText("Title"), "Thesis draft");
    await userEvent.click(screen.getByRole("button", { name: "Link" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        provider: "overleaf",
        url: "https://www.overleaf.com/project/0123456789abcdef01234567",
        title: "Thesis draft",
      }),
    );
  });

  it("shows the server's error for a pasted URL", async () => {
    setup([LINK_ONLY], {
      [`POST ${LINKS}`]: { status: 400, body: { url: ["That address is not allowed."] } },
    });
    renderRoute(FILES);
    await openMenu();
    await userEvent.click(await screen.findByRole("menuitem", { name: /Overleaf/ }));
    await userEvent.type(
      await screen.findByLabelText("Overleaf link"),
      "https://www.overleaf.com/project/0123456789abcdef01234567",
    );
    await userEvent.type(screen.getByLabelText("Title"), "T");
    await userEvent.click(screen.getByRole("button", { name: "Link" }));
    expect(await screen.findByText("That address is not allowed.")).toBeVisible();
  });
});

describe("checkPastedUrl", () => {
  it("fullmatches the pattern and tolerates none", () => {
    const p = LINK_ONLY as never;
    expect(checkPastedUrl("", p)).toBe("Paste a link.");
    expect(checkPastedUrl("not a url", p)).toMatch(/full web address/);
    expect(
      checkPastedUrl("https://www.overleaf.com/project/0123456789abcdef01234567/x", p),
    ).toMatch(/does not look like/);
    expect(checkPastedUrl("https://anything.test/x", { ...PUBLIC, url_pattern: "" } as never)).toBe(
      "",
    );
  });
});
