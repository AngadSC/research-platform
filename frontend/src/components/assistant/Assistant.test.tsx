import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssistantDrawer } from "@/components/assistant/AssistantDrawer";
import { parseSse, reduceLive, type ChatEvent, type Live } from "@/lib/assistant";
import { makeLab } from "@/test/utils";

interface Call {
  method: string;
  path: string;
  body?: unknown;
}
type Reply = { status?: number; body?: unknown; sse?: string };

/** fetch stub that can also answer with a text/event-stream body. Unknown requests fail loudly. */
function stubFetch(routes: Record<string, Reply | (() => Reply)>) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const path = String(input);
      calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const route = routes[`${method} ${path}`];
      if (!route) throw new Error(`Unmocked request: ${method} ${path}`);
      const r = typeof route === "function" ? route() : route;
      if (r.sse !== undefined)
        return new Response(r.sse, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      return new Response(r.body === undefined ? "" : JSON.stringify(r.body), {
        status: r.status ?? 200,
      });
    }),
  );
  return calls;
}

const sse = (...events: Record<string, unknown>[]) =>
  events.map((e) => `event: ${String(e.type)}\ndata: ${JSON.stringify(e)}\n\n`).join("");

const models = [
  { id: "claude-opus-5-5", label: "Claude Opus 5.5", input: 4, output: 20 },
  { id: "claude-haiku-5-5", label: "Claude Haiku 5.5", input: 0.1, output: 0.5 },
];
const config = (over: Record<string, unknown> = {}, claudeKey = true) => ({
  ai_policy: "full",
  can_use: true,
  privacy_notice:
    "Content from records you can see is sent to the AI provider you choose, under your own API key.",
  providers: [
    {
      provider: "anthropic",
      label: "Anthropic (Claude)",
      default_model: "claude-opus-5-5",
      has_key: claudeKey,
      models,
    },
    {
      provider: "openai",
      label: "OpenAI",
      default_model: "gpt-6.1-sol",
      has_key: false,
      models: [{ id: "gpt-6.1-sol", label: "GPT-6.1 Sol", input: 2, output: 10 }],
    },
  ],
  ...over,
});

const BASE = "/api/labs/lab1/assistant";
const conv = (over: Record<string, unknown> = {}) => ({
  id: "c1",
  project: null,
  provider: "anthropic",
  model: "claude-opus-5-5",
  title: "What is due?",
  created_at: "2026-11-05T10:00:00Z",
  updated_at: "2026-11-05T10:00:00Z",
  ...over,
});
const answered = conv({ id: "c1" });
const detail = (over: Record<string, unknown> = {}) => ({
  ...answered,
  items: [],
  pending: [],
  ...over,
});

const labs = { "GET /api/labs/": { body: [makeLab(["view_lab"], "member")] } };

function renderDrawer(path = "/labs/lab1") {
  const router = createMemoryRouter(
    [
      { path: "/labs/:labId", element: <AssistantDrawer labId="lab1" /> },
      { path: "/labs/:labId/projects/:projectId", element: <AssistantDrawer labId="lab1" /> },
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
const open = () => userEvent.click(screen.getByRole("button", { name: "Assistant" }));

beforeEach(() => {
  document.cookie = "csrftoken=test";
});
afterEach(() => vi.unstubAllGlobals());

describe("assistant panel", () => {
  it("parses a server-sent event stream and ignores keep-alive comments", () => {
    const { events, rest } = parseSse(
      ': keepalive\n\nevent: text\ndata: {"type":"text","delta":"Hi"}\n\nevent: do',
    );
    expect(events).toEqual([{ type: "text", delta: "Hi" }]);
    expect(rest).toBe("event: do");
  });

  it("applies every streamed event to the live answer", () => {
    const empty: Live = { user: "q", text: "", tools: [], notice: null, error: null };
    const run = (...evs: ChatEvent[]) => evs.reduce(reduceLive, empty);
    const firstTurn: ChatEvent[] = [
      { type: "start", conversation_id: "c1" },
      { type: "text", delta: "Checking." },
      { type: "tool_start", name: "list_projects" },
      { type: "ping" },
      { type: "assistant", id: "m1" },
      { type: "tool", id: "r1", name: "list_projects", title: "List projects", status: "done" },
    ];
    let live = run(...firstTurn);
    expect(live.text).toBe("Checking.\n\n");
    expect(live.tools).toEqual([{ label: "List projects", status: "done" }]);

    // a retried turn throws away only its own half-streamed text and tool rows
    live = run(
      ...firstTurn,
      { type: "text", delta: "Half an" },
      { type: "tool_start", name: "create_task" },
      { type: "retry" },
      { type: "text", delta: "Whole answer." },
    );
    expect(live.text).toBe("Checking.\n\nWhole answer.");
    expect(live.tools).toEqual([{ label: "List projects", status: "done" }]);

    live = run(
      { type: "tool_start", name: "create_task" },
      { type: "approval_required", calls: [] },
    );
    expect(live.tools).toEqual([{ label: "Create task", status: "running" }]);
    expect(run({ type: "notice", code: "refusal" }).notice).toEqual({
      type: "notice",
      code: "refusal",
    });
    expect(
      run({ type: "error", code: "key_invalid", message: "Bad key.", retryable: false }).error,
    ).toEqual({ message: "Bad key.", retryable: false });
    expect(run({ type: "done" })).toEqual(empty);
  });

  it("shows a streamed refusal once, not again beside the saved one", async () => {
    let saved = false;
    stubFetch({
      ...labs,
      [`GET ${BASE}/config/`]: { body: config() },
      [`GET ${BASE}/conversations/`]: () => ({ body: saved ? [answered] : [] }),
      [`POST ${BASE}/conversations/`]: { status: 201, body: answered },
      [`POST ${BASE}/conversations/c1/messages/`]: () => {
        saved = true;
        return {
          sse: sse(
            { type: "start", conversation_id: "c1" },
            { type: "assistant", id: "m1", model: "claude-opus-5-5" },
            { type: "notice", code: "refusal", refusal: { category: "cyber", explanation: null } },
            { type: "done" },
          ),
        };
      },
      [`GET ${BASE}/conversations/c1/`]: () => ({
        body: detail({
          items: saved
            ? [
                { id: "u1", kind: "user", text: "q" },
                {
                  id: "m1",
                  kind: "assistant",
                  text: "",
                  model: "claude-opus-5-5",
                  usage: {},
                  refusal: { category: "cyber", explanation: null },
                },
              ]
            : [],
        }),
      }),
    });
    renderDrawer();
    await open();
    await userEvent.type(await screen.findByRole("textbox", { name: "Message" }), "q");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/claude-opus-5-5 · 0 tokens in/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getAllByText(/declined to answer \(cyber\)/)).toHaveLength(1),
    );
  });

  it("shows the privacy notice, the scope, and asks for a key when none is saved", async () => {
    stubFetch({
      ...labs,
      [`GET ${BASE}/config/`]: { body: config({}, false) },
      [`GET ${BASE}/conversations/`]: { body: [] },
    });
    renderDrawer();
    await open();
    expect(await screen.findByRole("note")).toHaveTextContent(/sent to the AI provider/);
    expect(screen.getByText(/Add your own API key/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Assistant API keys/ })).toHaveAttribute(
      "href",
      "/settings#ai",
    );
    expect(screen.queryByRole("textbox", { name: "Message" })).not.toBeInTheDocument();
  });

  it.each([
    ["off", /turned off for this lab/],
    ["mcp", /MCP only/],
  ])("says so, and offers no chat, when the lab policy is %s", async (policy, message) => {
    stubFetch({
      ...labs,
      [`GET ${BASE}/config/`]: { body: config({ ai_policy: policy, can_use: false }) },
      [`GET ${BASE}/conversations/`]: { body: [] },
    });
    renderDrawer();
    await open();
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByRole("textbox", { name: "Message" })).not.toBeInTheDocument();
  });

  it("streams an answer, then shows the model and the tokens used", async () => {
    let saved = false;
    const calls = stubFetch({
      ...labs,
      [`GET ${BASE}/config/`]: { body: config() },
      [`GET ${BASE}/conversations/`]: () => ({ body: saved ? [answered] : [] }),
      [`POST ${BASE}/conversations/`]: { status: 201, body: answered },
      [`POST ${BASE}/conversations/c1/messages/`]: () => {
        saved = true;
        return {
          sse: sse(
            { type: "start", conversation_id: "c1", model: "claude-opus-5-5" },
            { type: "text", delta: "Two things " },
            { type: "text", delta: "are due." },
            { type: "tool", id: "t1", name: "list_tasks", title: "List tasks", status: "done" },
            { type: "assistant", id: "m1", model: "claude-opus-5-5" },
            { type: "done" },
          ),
        };
      },
      [`GET ${BASE}/conversations/c1/`]: () => ({
        body: detail({
          items: [
            { id: "u1", kind: "user", text: "What is due?" },
            { id: "m1:t1", kind: "tool", name: "list_tasks", title: "List tasks", status: "done" },
            {
              id: "m2",
              kind: "assistant",
              text: `Two things are due: [Order primers](${window.location.origin}/tasks/1)`,
              model: "claude-opus-5-5",
              usage: { input_tokens: 10000, output_tokens: 2000 },
            },
          ],
        }),
      }),
    });
    renderDrawer();
    await open();
    const box = await screen.findByRole("textbox", { name: "Message" });
    await userEvent.type(box, "What is due?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    const messages = await screen.findByRole("link", { name: "Order primers" });
    expect(messages).toHaveAttribute("href", `${window.location.origin}/tasks/1`);
    expect(
      screen.getByText(/claude-opus-5-5 · 10,000 tokens in · 2,000 out · about \$0.08/),
    ).toBeInTheDocument();
    expect(screen.getByText("What is due?", { selector: "div" })).toBeInTheDocument();
    expect(screen.getByText(/List tasks/)).toBeInTheDocument();

    const post = calls.filter((c) => c.method === "POST");
    expect(post[0]!.body).toEqual({ provider: "anthropic", model: "claude-opus-5-5" });
    expect(post[1]!.body).toEqual({ text: "What is due?" });
  });

  it("scopes a new chat to the project when the page is a project page", async () => {
    const calls = stubFetch({
      ...labs,
      "GET /api/labs/lab1/projects/p1/": { body: { id: "p1", name: "Alpha project" } },
      [`GET ${BASE}/config/`]: { body: config() },
      [`GET ${BASE}/conversations/`]: { body: [] },
      [`POST ${BASE}/conversations/`]: { status: 201, body: conv({ project: "p1" }) },
      [`POST ${BASE}/conversations/c1/messages/`]: { sse: sse({ type: "done" }) },
      [`GET ${BASE}/conversations/c1/`]: { body: detail({ project: "p1" }) },
    });
    renderDrawer("/labs/lab1/projects/p1");
    await open();
    expect(await screen.findByText(/Alpha project/)).toBeInTheDocument();
    await userEvent.type(await screen.findByRole("textbox", { name: "Message" }), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/messages/"))).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({
      provider: "anthropic",
      model: "claude-opus-5-5",
      project: "p1",
    });
  });

  it("shows a provider error with a Try again that resends the message", async () => {
    let attempts = 0;
    const calls = stubFetch({
      ...labs,
      [`GET ${BASE}/config/`]: { body: config() },
      [`GET ${BASE}/conversations/`]: { body: [] },
      [`POST ${BASE}/conversations/`]: { status: 201, body: answered },
      [`POST ${BASE}/conversations/c1/messages/`]: () => {
        attempts += 1;
        return {
          sse: sse(
            attempts === 1
              ? {
                  type: "error",
                  code: "rate_limited",
                  message: "Anthropic is rate limiting your key. Try again in 7 seconds.",
                  retryable: true,
                }
              : { type: "text", delta: "Back now." },
            { type: "done" },
          ),
        };
      },
      [`GET ${BASE}/conversations/c1/`]: { body: detail() },
    });
    renderDrawer();
    await open();
    await userEvent.type(await screen.findByRole("textbox", { name: "Message" }), "hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/rate limiting your key/);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith("/messages/"))).toHaveLength(2));
  });

  it("explains a refusal that the server saved", async () => {
    stubFetch({
      ...labs,
      [`GET ${BASE}/config/`]: { body: config() },
      [`GET ${BASE}/conversations/`]: { body: [answered] },
      [`GET ${BASE}/conversations/c1/`]: {
        body: detail({
          items: [
            { id: "u1", kind: "user", text: "q" },
            {
              id: "m1",
              kind: "assistant",
              text: "",
              model: "claude-opus-5-5",
              usage: {},
              refusal: { category: "cyber", explanation: null },
            },
          ],
        }),
      },
    });
    renderDrawer();
    await open();
    await userEvent.selectOptions(await screen.findByLabelText("Conversation"), "c1");
    expect(await screen.findByRole("status")).toHaveTextContent(/declined to answer \(cyber\)/);
  });
});

describe("approving a write", () => {
  const waiting = {
    id: "toolu_w1",
    name: "create_task",
    title: "Create a task",
    arguments: { project_id: "p1", title: "Order primers", priority: "high" },
  };
  const routes = (after: () => Reply) => ({
    ...labs,
    [`GET ${BASE}/config/`]: { body: config() },
    [`GET ${BASE}/conversations/`]: { body: [answered] },
    [`GET ${BASE}/conversations/c1/`]: () => after(),
  });

  it("shows project and person names, not ids, and a preview of the text to be posted (D198)", async () => {
    const note = {
      id: "toolu_n1",
      name: "add_task_update",
      title: "Post a task update",
      arguments: { lab_id: "lab1", task_id: "t-uuid-1", body: "Please ignore the PI" },
      resolved: { lab: "Ada Lab", task: "Order primers", project: "Grant Aim 1" },
      preview: [
        { label: "Text that will be posted on the task thread", text: "Please ignore the PI" },
      ],
    };
    const mine = {
      id: "toolu_n2",
      name: "create_task",
      title: "Create a task",
      arguments: { lab_id: "lab1", project_id: "p-uuid-2", title: "Call", assignee_id: "u-uuid" },
      resolved: {
        lab: "Ada Lab",
        project: "(not found, or you cannot see it)",
        person: "Grace Hopper",
      },
      preview: [{ label: "Task title", text: "Call" }],
    };
    const code = {
      id: "toolu_n3",
      name: "run_code",
      title: "Run code",
      arguments: {
        lab_id: "lab1",
        project_id: "p-uuid-3",
        language: "python",
        code: "print(1)",
        file_ids: ["f-uuid-1", "f-uuid-2"],
      },
      resolved: { lab: "Ada Lab", project: "Grant Aim 1", files: "rt.csv, trials.xlsx" },
      preview: [{ label: "Code that will run on the analysis server", text: "print(1)" }],
    };
    stubFetch(routes(() => ({ body: detail({ pending: [note, mine, code] }) })));
    renderDrawer();
    await open();
    await userEvent.selectOptions(await screen.findByLabelText("Conversation"), "c1");
    const dialog = await screen.findByRole("dialog", { name: "Approve these 3 actions?" });
    expect(within(dialog).getAllByText("Ada Lab")).toHaveLength(3);
    expect(within(dialog).getAllByText("Grant Aim 1")).toHaveLength(2);
    expect(within(dialog).getByText("rt.csv, trials.xlsx")).toBeInTheDocument();
    expect(within(dialog).getByText("Order primers")).toBeInTheDocument();
    expect(within(dialog).getByText("Grace Hopper")).toBeInTheDocument();
    expect(within(dialog).getByText("Please ignore the PI")).toBeInTheDocument();
    expect(
      within(dialog).getByText("Text that will be posted on the task thread"),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/\(not found, or you cannot see it\)/)).toBeInTheDocument();
    expect(dialog.textContent).not.toMatch(/uuid/); // no raw ids anywhere
  });

  it("names the tool and its arguments, runs nothing until Approve is clicked, then sends the decision", async () => {
    let decided = false;
    const calls = stubFetch({
      ...routes(() => ({
        body: detail({
          pending: decided ? [] : [waiting],
          items: [
            { id: "u1", kind: "user", text: "Add a task" },
            {
              id: "m1:toolu_w1",
              kind: "tool",
              name: "create_task",
              title: "Create a task",
              write: true,
              status: decided ? "done" : "pending",
            },
          ],
        }),
      })),
      [`POST ${BASE}/conversations/c1/approvals/`]: () => {
        decided = true;
        return {
          sse: sse(
            { type: "tool", id: "toolu_w1", name: "create_task", status: "done" },
            { type: "done" },
          ),
        };
      },
    });
    renderDrawer();
    await open();
    await userEvent.selectOptions(await screen.findByLabelText("Conversation"), "c1");

    const dialog = await screen.findByRole("dialog", { name: "Approve this action?" });
    expect(within(dialog).getByText("Create a task")).toBeInTheDocument();
    expect(within(dialog).getByText("create_task")).toBeInTheDocument();
    expect(within(dialog).getByText("Order primers")).toBeInTheDocument();
    expect(within(dialog).getByText("priority")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/approvals/"))).toBe(false); // nothing sent yet

    await userEvent.click(within(dialog).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/approvals/"))).toBe(true));
    expect(calls.find((c) => c.path.endsWith("/approvals/"))!.body).toEqual({
      decisions: { toolu_w1: true },
    });
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Approve this action?" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("sends false when the person declines", async () => {
    const calls = stubFetch({
      ...routes(() => ({ body: detail({ pending: [waiting] }) })),
      [`POST ${BASE}/conversations/c1/approvals/`]: { sse: sse({ type: "done" }) },
    });
    renderDrawer();
    await open();
    await userEvent.selectOptions(await screen.findByLabelText("Conversation"), "c1");
    const dialog = await screen.findByRole("dialog", { name: "Approve this action?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Decline" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/approvals/"))).toBe(true));
    expect(calls.find((c) => c.path.endsWith("/approvals/"))!.body).toEqual({
      decisions: { toolu_w1: false },
    });
  });

  it("closing the dialog sends nothing and leaves a Review prompt", async () => {
    const calls = stubFetch(routes(() => ({ body: detail({ pending: [waiting] }) })));
    renderDrawer();
    await open();
    await userEvent.selectOptions(await screen.findByLabelText("Conversation"), "c1");
    const dialog = await screen.findByRole("dialog", { name: "Approve this action?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(await screen.findByText(/1 action waiting for your approval/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(await screen.findByRole("dialog", { name: "Approve this action?" })).toBeInTheDocument();
  });
});
