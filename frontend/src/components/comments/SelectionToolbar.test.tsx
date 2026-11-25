import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada Lee" };

function setup(aiReady: boolean, grants: unknown[] = []) {
  return mockFetch({
    [SESSION]: signedIn,
    "GET /api/ai/grants/": { body: grants },
    "GET /api/me/": { body: user },
    "GET /api/labs/": { body: [makeLab(["view_lab"])] },
    "GET /api/labs/lab1/": { body: makeLab(["view_lab"]) },
    "GET /api/labs/lab1/projects/": { body: [] },
    "GET /api/labs/lab1/members/": { body: [] },
    "GET /api/labs/lab1/my-tasks/": { body: [] },
    "GET /api/labs/lab1/getting-started/": { status: 404, body: {} },
    "GET /api/labs/lab1/assistant/config/": {
      body: {
        can_use: aiReady,
        providers: aiReady ? [{ provider: "claude", has_key: true, default_model: "m" }] : [],
      },
    },
    "GET /api/labs/lab1/page-comments/?path=%2Flabs%2Flab1%2Fdashboard": { body: [] },
    "POST /api/labs/lab1/page-comments/": {
      status: 201,
      body: {
        id: "c1",
        author: user,
        path: "/labs/lab1/dashboard",
        page_label: "",
        quote: "",
        body: "",
        created_at: "2030-01-01T00:00:00Z",
      },
    },
  });
}

/** Select the text of an element in the page's main area, as a drag would. */
async function select() {
  const el = await waitFor(() => {
    const found = [...document.querySelectorAll("#main h1, #main h2, #main p")].find(
      (n) => (n.textContent ?? "").trim().length > 3,
    );
    if (!found) throw new Error("page not ready");
    return found;
  });
  const range = document.createRange();
  range.selectNodeContents(el);
  range.getBoundingClientRect = () =>
    ({ left: 100, top: 200, width: 80, height: 20, right: 180, bottom: 220 }) as DOMRect;
  act(() => {
    const sel = window.getSelection()!;
    sel.removeAllRanges();
    sel.addRange(range);
    document.dispatchEvent(new Event("selectionchange"));
  });
}

beforeEach(() => {
  window.getSelection()?.removeAllRanges();
  Element.prototype.scrollIntoView = () => {};
});

describe("the buttons over selected text", () => {
  it("offers a comment button, and posts the comment with the selected text as its quote", async () => {
    const calls = setup(false);
    renderRoute("/labs/lab1/dashboard");
    await select();
    await userEvent.click(await screen.findByRole("button", { name: "Comment on this" }));
    expect(screen.queryByRole("button", { name: "Summarize this" })).toBeNull(); // no AI connected
    await userEvent.type(await screen.findByLabelText("Your comment"), "Looks right");
    await userEvent.click(screen.getByRole("button", { name: "Comment" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({
      path: "/labs/lab1/dashboard",
      body: "Looks right",
    });
  });

  it("offers Summarize only when an AI is connected", async () => {
    setup(true);
    renderRoute("/labs/lab1/dashboard");
    await select();
    expect(await screen.findByRole("button", { name: "Summarize this" })).toBeInTheDocument();
  });

  it("offers Summarize when Claude is connected without a key, and opens it beside the page", async () => {
    setup(false, [
      {
        id: "g1",
        kind: "oauth",
        client_name: "Claude",
        revoked_at: null,
        labs: [],
        access: "read",
      },
    ]);
    const open = vi.spyOn(window, "open").mockReturnValue({} as Window);
    renderRoute("/labs/lab1/dashboard");
    await select();
    await userEvent.click(await screen.findByRole("button", { name: "Summarize this" }));
    expect(open).toHaveBeenCalledTimes(1);
    const url = String(open.mock.calls[0]![0]);
    expect(url.startsWith("https://claude.ai/new?q=")).toBe(true);
    expect(decodeURIComponent(url.split("?q=")[1]!)).toMatch(/^Summarize this: /);
    open.mockRestore();
  });
});
