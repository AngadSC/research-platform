import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Link, Outlet, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssistantDrawer } from "@/components/assistant/AssistantDrawer";
import { makeLab } from "@/test/utils";

const P1 = "11111111-1111-4111-8111-111111111111";
const D1 = "22222222-2222-4222-8222-222222222222";
const BASE = "/api/labs/lab1/assistant";
const cfg = {
  ai_policy: "full",
  can_use: true,
  privacy_notice: "Notice.",
  providers: [
    {
      provider: "anthropic",
      label: "Anthropic (Claude)",
      default_model: "m1",
      has_key: true,
      models: [{ id: "m1", label: "M1", input: 1, output: 1 }],
    },
  ],
};
const conv = {
  id: "c1",
  project: P1,
  provider: "anthropic",
  model: "m1",
  title: "",
  created_at: "2026-11-05T10:00:00Z",
  updated_at: "2026-11-05T10:00:00Z",
};

function stubFetch() {
  const bodies: Record<string, unknown> = {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${String(input)}`;
      if (init?.body) bodies[key] = JSON.parse(String(init.body));
      const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
      if (key === "GET /api/labs/") return json([makeLab(["view_lab"], "member")]);
      if (key === `GET ${BASE}/config/`) return json(cfg);
      if (key === `GET ${BASE}/conversations/`) return json([]);
      if (key === `POST ${BASE}/conversations/`) return json(conv, 201);
      if (key === `GET ${BASE}/conversations/c1/`) return json({ ...conv, items: [], pending: [] });
      if (key === `POST ${BASE}/conversations/c1/messages/`)
        return new Response('event: done\ndata: {"type":"done"}\n\n', {
          headers: { "Content-Type": "text/event-stream" },
        });
      if (key.startsWith("GET /api/labs/lab1/projects/"))
        return json({ id: P1, name: "Alpha project" });
      throw new Error(`Unmocked request: ${key}`);
    }),
  );
  return bodies;
}

function renderApp(path = `/labs/lab1/projects/${P1}`) {
  const router = createMemoryRouter(
    [
      {
        path: "/labs/:labId",
        element: (
          <>
            <AssistantDrawer labId="lab1" />
            <Link to="/labs/lab1/other">Other page</Link>
            <Outlet />
          </>
        ),
        children: [
          { path: "other", element: <p>The other page</p> },
          { path: "projects/:projectId", element: <p>A project</p> },
          { path: "projects/:projectId/documents/:documentId", element: <p>A document</p> },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

const KEY = "assistant-dock";
const saved = () =>
  JSON.parse(localStorage.getItem(KEY) ?? "{}") as { mode?: string; width?: number };
const wideBefore = window.matchMedia;

beforeEach(() => {
  document.cookie = "csrftoken=test";
  localStorage.clear();
  window.matchMedia = ((query: string) => ({
    matches: true,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
});
afterEach(() => {
  window.matchMedia = wideBefore;
  vi.unstubAllGlobals();
  document.documentElement.style.removeProperty("--assistant-w");
});

describe("docked assistant", () => {
  it("docks on the right, makes room, stays on route change, and remembers its state", async () => {
    stubFetch();
    renderApp();
    expect(screen.queryByRole("complementary", { name: "Assistant" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Assistant" }));

    const dock = await screen.findByRole("complementary", { name: "Assistant" });
    expect(dock).toHaveStyle({ width: "384px" });
    expect(document.documentElement.style.getPropertyValue("--assistant-w")).toBe("384px");
    expect(saved()).toMatchObject({ mode: "open", width: 384 });

    // the typed text survives a move to another page: the panel is not remounted
    const box = await screen.findByRole("textbox", { name: "Message" });
    await userEvent.type(box, "half a thought");
    await userEvent.click(screen.getByRole("link", { name: "Other page" }));
    expect(await screen.findByText("The other page")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("half a thought");

    // resize with the keyboard, then collapse to a strip
    screen.getByRole("separator", { name: "Resize the assistant" }).focus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(saved().width).toBe(408);
    await userEvent.click(
      screen.getByRole("button", { name: "Collapse the assistant to a side strip" }),
    );
    expect(saved().mode).toBe("strip");
    expect(document.documentElement.style.getPropertyValue("--assistant-w")).toBe("40px");
    await userEvent.click(screen.getByRole("button", { name: "Open the assistant" }));
    expect(saved().mode).toBe("open");
  });

  it("starts as it was left, and toggles with the keyboard shortcut", async () => {
    localStorage.setItem(KEY, JSON.stringify({ mode: "open", width: 9999 }));
    stubFetch();
    renderApp();
    const dock = await screen.findByRole("complementary", { name: "Assistant" });
    expect(dock).toHaveStyle({ width: `${Math.max(320, Math.min(640, window.innerWidth / 2))}px` });

    await userEvent.keyboard("{Control>}.{/Control}");
    await waitFor(() => expect(saved().mode).toBe("closed"));
    expect(screen.getByRole("button", { name: "Assistant" })).toHaveAttribute("title");
    await userEvent.keyboard("{Control>}.{/Control}");
    await waitFor(() => expect(saved().mode).toBe("open"));
  });

  it("sends the open page as kind and ids only", async () => {
    const bodies = stubFetch();
    renderApp(`/labs/lab1/projects/${P1}/documents/${D1}`);
    await userEvent.click(screen.getByRole("button", { name: "Assistant" }));
    await userEvent.type(await screen.findByRole("textbox", { name: "Message" }), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(bodies[`POST ${BASE}/conversations/c1/messages/`]).toBeDefined());
    expect(bodies[`POST ${BASE}/conversations/c1/messages/`]).toEqual({
      text: "hi",
      page: { kind: "document", id: D1, project: P1 },
    });
  });
});
