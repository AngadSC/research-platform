import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const person = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const other = { id: "u2", email: "bo@uni.edu", display_name: "Bo" };
const row = {
  id: "p1",
  title: "Attention is all you need",
  authors: ["Vaswani, Ashish", "Google Brain,"],
  year: 2017,
  venue: "NeurIPS",
  doi: "10.5555/3295222",
  url: "",
  added_by: person,
  created_at: "2026-01-01T00:00:00Z",
  has_pdf: true,
  note_count: 1,
};
const detail = {
  ...row,
  abstract: "We propose a model.",
  notes: [
    {
      id: "n1",
      paper: "p1",
      author: other,
      body: "Useful results",
      created_at: "2026-01-02T00:00:00Z",
      edited_at: null,
    },
  ],
  pdf: {
    id: "att1",
    project: null,
    ethics_approval: null,
    original_filename: "a.pdf",
    content_type: "application/pdf",
    size_bytes: 10,
    sha256: "x",
    uploaded_by: person,
    notice_acknowledged_at: "2026-01-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
  },
};
const citations = { apa: "APA text", mla: "MLA text", chicago: "Chicago text", bibtex: "@misc{x}" };
const config = (over: Record<string, unknown> = {}) => ({
  ai_policy: "full",
  can_use: true,
  privacy_notice: "Sent to the provider.",
  providers: [
    {
      provider: "anthropic",
      label: "Claude",
      default_model: "m",
      has_key: true,
      models: [{ id: "m", label: "M", input: 1, output: 1 }],
    },
  ],
  ...over,
});

const handlers = (perms: string[], cfg = config()) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(perms)] },
  "GET /api/labs/lab1/": { body: makeLab(perms) },
  "GET /api/labs/lab1/projects/": { body: [] },
  "GET /api/labs/lab1/notifications/": { body: [] },
  "GET /api/labs/lab1/chat/unread/": { body: [] },
  "GET /api/labs/lab1/papers/?q=": { body: [row] },
  "GET /api/labs/lab1/papers/p1/": { body: detail },
  "GET /api/labs/lab1/papers/p1/citation/": { body: citations },
  "GET /api/labs/lab1/assistant/config/": { body: cfg },
  "GET /api/labs/lab1/assistant/conversations/": { body: [] },
});

afterEach(() => vi.unstubAllGlobals());

describe("paper list", () => {
  it("shows papers, the organisation without its comma marker, and Add for contributors", async () => {
    mockFetch(handlers(["view_lab", "contribute_lab"]));
    renderRoute("/labs/lab1/papers");
    expect(await screen.findByRole("link", { name: row.title })).toBeInTheDocument();
    expect(screen.getByText("Vaswani, Ashish and 1 more")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add paper" })).toBeInTheDocument();
  });

  it("offers no Add to a lab viewer", async () => {
    mockFetch(handlers(["view_lab"]));
    renderRoute("/labs/lab1/papers");
    await screen.findByRole("link", { name: row.title });
    expect(screen.queryByRole("button", { name: "Add paper" })).not.toBeInTheDocument();
  });
});

describe("paper detail", () => {
  it("shows metadata, notes with author, and copies the chosen citation style", async () => {
    mockFetch(handlers(["view_lab", "contribute_lab"]));
    renderRoute("/labs/lab1/papers/p1");
    expect(await screen.findByText("Useful results")).toBeInTheDocument();
    expect(screen.getByText("Bo")).toBeInTheDocument();
    expect(await screen.findByText("APA text")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Citation style"), "bibtex");
    expect(screen.getByText("@misc{x}")).toBeInTheDocument();
    const write = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText: write } });
    await userEvent.click(screen.getByRole("button", { name: /Copy citation/ }));
    await waitFor(() => expect(write).toHaveBeenCalledWith("@misc{x}"));
  });

  it("opens the assistant with a prefilled prompt naming this paper", async () => {
    mockFetch(handlers(["view_lab", "contribute_lab"]));
    renderRoute("/labs/lab1/papers/p1");
    await userEvent.click(await screen.findByRole("button", { name: /Generate notes with AI/ }));
    const box = await screen.findByRole("textbox", { name: "Message" });
    expect((box as HTMLTextAreaElement).value).toContain("Attention is all you need");
    expect((box as HTMLTextAreaElement).value).toContain("paper_id p1");
    expect((box as HTMLTextAreaElement).value).toContain("read_paper");
  });

  it.each([
    [config({ ai_policy: "off", can_use: false }), /turned off for this lab/],
    [config({ ai_policy: "mcp", can_use: false }), /MCP only/],
    [config({ providers: [{ ...config().providers[0], has_key: false }] }), /Add your own API key/],
  ])("explains instead of offering AI buttons (%#)", async (cfg, message) => {
    mockFetch(handlers(["view_lab", "contribute_lab"], cfg));
    renderRoute("/labs/lab1/papers/p1");
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Generate notes/ })).not.toBeInTheDocument();
  });

  it("hides note and upload controls from a lab viewer", async () => {
    mockFetch(handlers(["view_lab"]));
    renderRoute("/labs/lab1/papers/p1");
    await screen.findByText("Useful results");
    expect(screen.queryByRole("button", { name: "Add note" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Replace PDF/ })).not.toBeInTheDocument();
  });
});

describe("paper delete", () => {
  it("confirms in a dialog, then leaves without fetching the deleted paper again", async () => {
    const confirm = vi.spyOn(window, "confirm");
    const calls = mockFetch({
      ...handlers(["view_lab", "contribute_lab", "manage_lab"]),
      "DELETE /api/labs/lab1/papers/p1/": { status: 204 },
    });
    renderRoute("/labs/lab1/papers/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(confirm).not.toHaveBeenCalled();
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    const before = calls.length;
    await userEvent.click(await screen.findByRole("button", { name: "Delete paper" }));
    expect(await screen.findByRole("link", { name: row.title })).toBeInTheDocument();
    const after = calls.slice(before).map((c) => c.path);
    expect(after.filter((p) => p.includes("/papers/p1/"))).toEqual(["/api/labs/lab1/papers/p1/"]);
  });
});
