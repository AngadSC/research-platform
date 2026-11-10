import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { daysUntil, expiryTone, validateApproval } from "@/lib/ethics";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const iso = (offset: number) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const approval = (over: Record<string, unknown> = {}) => ({
  id: "ap1",
  approval_number: "IRB-1",
  board: "Example IRB",
  title: "Attention study",
  approval_date: iso(-300),
  expiry_date: iso(25),
  status: "active",
  restricted: false,
  projects: [{ id: "p1", name: "Gut study" }],
  attachments: [],
  can_view_files: true,
  created_by: user,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...over,
});
const note = (id: string, read: string | null = null) => ({
  id,
  kind: "ethics_expiry",
  title: `Expires soon ${id}`,
  body: "",
  target_type: "ethics.EthicsApproval",
  target_id: "ap1",
  read_at: read,
  created_at: "2026-01-01T00:00:00Z",
});
const base = (perms: string[]) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(perms)] },
  "GET /api/labs/lab1/": { body: makeLab(perms) },
  "GET /api/labs/lab1/projects/": { body: [] },
  "GET /api/labs/lab1/notifications/": { body: [] },
});

describe("expiry tone", () => {
  it.each([
    [61, "active", "success"],
    [25, "active", "warning"],
    [5, "active", "destructive"],
    [-3, "active", "destructive"],
    [40, "expired", "destructive"],
  ])("%i days, %s -> %s", (days, status, tone) => {
    expect(expiryTone(days, status)).toBe(tone);
  });

  it("counts whole days from the local date", () => {
    expect(daysUntil(iso(25))).toBe(25);
    expect(daysUntil(iso(-1))).toBe(-1);
  });
});

describe("validation", () => {
  const ok = {
    approval_number: "A",
    board: "B",
    title: "T",
    approval_date: "2026-03-01",
    expiry_date: "2027-03-01",
  };
  it("rejects expiry on or before the approval date", () => {
    expect(validateApproval(ok)).toEqual({});
    expect(validateApproval({ ...ok, expiry_date: "2026-02-01" }).expiry_date).toMatch(/after/);
    expect(validateApproval({ ...ok, expiry_date: "2026-03-01" }).expiry_date).toMatch(/after/);
  });

  it("shows the message inline and does not submit", async () => {
    const calls = mockFetch({
      ...base(["view_lab", "view_ethics", "edit_ethics"]),
    });
    renderRoute("/labs/lab1/ethics/new");
    const u = userEvent.setup();
    await u.type(await screen.findByLabelText("Approval number"), "A");
    await u.type(screen.getByLabelText("Ethics board"), "B");
    await u.type(screen.getByLabelText("Title"), "T");
    await u.type(screen.getByLabelText("Approval date"), "2026-03-01");
    await u.type(screen.getByLabelText("Expiry date"), "2026-02-01");
    await u.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Expiry must be after the approval date")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path.includes("ethics"))).toBe(false);
  });
});

describe("list", () => {
  it("shows a relative expiry label and a warning badge", async () => {
    mockFetch({
      ...base(["view_lab", "view_ethics"]),
      "GET /api/labs/lab1/ethics-approvals/": { body: [approval()] },
    });
    renderRoute("/labs/lab1/ethics");
    expect(await screen.findByText("in 25 days")).toBeInTheDocument();
    expect(screen.getByText("active", { selector: "span[data-days]" })).toHaveClass("bg-warning");
  });

  it("explains an empty list", async () => {
    mockFetch({
      ...base(["view_lab", "view_ethics"]),
      "GET /api/labs/lab1/ethics-approvals/": { body: [] },
    });
    renderRoute("/labs/lab1/ethics");
    expect(await screen.findByText("No ethics approvals yet")).toBeInTheDocument();
  });
});

describe("notifications bell", () => {
  it("shows the unread count and Mark all calls the endpoint", async () => {
    const calls = mockFetch({
      ...base(["view_lab"]),
      "GET /api/labs/lab1/notifications/": {
        body: [note("n1"), note("n2"), note("n3", "2026-01-02T00:00:00Z")],
      },
      "POST /api/labs/lab1/notifications/read-all/": { body: { updated: 2 } },
    });
    document.cookie = "csrftoken=t";
    renderRoute("/labs/lab1/notifications");
    const bell = await screen.findByRole("button", { name: "Notifications, 2 unread" });
    expect(within(bell).getByTestId("unread-count")).toHaveTextContent("2");
    await userEvent.click(bell);
    await userEvent.click(
      within(await screen.findByRole("menu")).getByRole("button", { name: "Mark all as read" }),
    );
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/read-all/"))).toBe(true),
    );
  });

  it("has an empty state on the full page", async () => {
    mockFetch(base(["view_lab"]));
    renderRoute("/labs/lab1/notifications");
    expect(await screen.findByText("You are all caught up")).toBeInTheDocument();
  });
});

describe("retention review", () => {
  it("is hidden from the sidebar and does not fetch without the permission", async () => {
    const calls = mockFetch(base(["view_lab"]));
    renderRoute("/labs/lab1/retention");
    expect(await screen.findByText(/for PIs and lab admins/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Retention" })).not.toBeInTheDocument();
    expect(calls.some((c) => c.path.includes("retention/due"))).toBe(false);
  });

  it("shows the banner and flags deleted items", async () => {
    mockFetch({
      ...base(["view_lab", "view_retention"]),
      "GET /api/labs/lab1/retention/due/": {
        body: [
          {
            kind: "project",
            id: "p9",
            name: "Old survey",
            project_id: "p9",
            project_name: "Old survey",
            retain_until: "2026-01-01",
            retention_note: "",
            deleted_at: "2026-02-01T00:00:00Z",
          },
        ],
      },
    });
    renderRoute("/labs/lab1/retention");
    expect(
      await screen.findByText(
        "Nothing is deleted automatically. Review each item and decide what to keep.",
      ),
    ).toBeInTheDocument();
    expect(await screen.findByText("Old survey")).toBeInTheDocument();
    expect(screen.getByText("Deleted")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Retention" })).toBeInTheDocument();
  });
});

class FakeXHR {
  static sent: { path: string; form: FormData }[] = [];
  upload = {};
  status = 201;
  responseText = "{}";
  path = "";
  onload?: () => void;
  open(_m: string, path: string) {
    this.path = path;
  }
  setRequestHeader() {}
  send(form: FormData) {
    FakeXHR.sent.push({ path: this.path, form });
    queueMicrotask(() => this.onload?.());
  }
}

describe("ethics upload", () => {
  beforeEach(() => {
    FakeXHR.sent = [];
    document.cookie = "csrftoken=t";
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("goes through the notice dialog and sends acknowledged_notice", async () => {
    mockFetch({
      ...base(["view_lab", "view_ethics", "edit_ethics"]),
      "GET /api/labs/lab1/ethics-approvals/ap1/": { body: approval() },
    });
    renderRoute("/labs/lab1/ethics/ap1");
    const u = userEvent.setup();
    await u.click(await screen.findByRole("button", { name: /upload file/i }));
    expect(screen.getByText(/Do not upload participant identifiers/)).toBeInTheDocument();
    await u.upload(
      screen.getByLabelText("Choose file"),
      new File(["%PDF"], "irb.pdf", { type: "application/pdf" }),
    );
    const send = screen.getByRole("button", { name: "Upload" });
    expect(send).toBeDisabled();
    await u.click(screen.getByRole("checkbox", { name: /no participant identifiers/i }));
    await u.click(send);
    await waitFor(() => expect(FakeXHR.sent).toHaveLength(1));
    expect(FakeXHR.sent[0]!.path).toBe("/api/labs/lab1/ethics-approvals/ap1/attachments/");
    expect(FakeXHR.sent[0]!.form.get("acknowledged_notice")).toBe("true");
  });
});
