import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: vi.fn(() => ({
    promise: Promise.resolve({
      numPages: 3,
      getPage: async () => ({
        getViewport: () => ({ width: 100, height: 100 }),
        render: () => ({ promise: Promise.resolve() }),
      }),
    }),
    destroy: vi.fn(),
  })),
}));

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const project = (perms: string[]) => ({
  id: "p1",
  name: "Gut study",
  description: "",
  status: "active",
  start_date: null,
  retain_until: null,
  retention_note: "",
  created_by: user,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  my_project_role: "lead",
  my_permissions: perms,
});
const att = {
  id: "a1",
  project: "p1",
  original_filename: "paper.pdf",
  content_type: "application/pdf",
  size_bytes: 2048,
  sha256: "x",
  uploaded_by: user,
  notice_acknowledged_at: "2026-01-01T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
};
const base = (perms: string[], files: unknown[] = []) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  "GET /api/labs/lab1/projects/": { body: [project(perms)] },
  "GET /api/labs/lab1/projects/p1/": { body: project(perms) },
  "GET /api/labs/lab1/projects/p1/attachments/": { body: files },
  "GET /api/labs/lab1/attachments/a1/": { body: att },
});
const FILES = "/labs/lab1/projects/p1/files";

class FakeXHR {
  static sent: FormData[] = [];
  upload: { onprogress?: unknown } = {};
  status = 201;
  responseText = JSON.stringify(att);
  onload?: () => void;
  onerror?: () => void;
  open() {}
  setRequestHeader() {}
  send(f: FormData) {
    FakeXHR.sent.push(f);
    queueMicrotask(() => this.onload?.());
  }
}

beforeEach(() => {
  FakeXHR.sent = [];
  document.cookie = "csrftoken=t";
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
});
afterEach(() => vi.unstubAllGlobals());

async function openDialog(u: ReturnType<typeof userEvent.setup>) {
  await u.click((await screen.findAllByRole("button", { name: /upload file/i }))[0]!);
  return screen.getByRole("dialog");
}
const pdf = () => new File(["%PDF"], "n.pdf", { type: "application/pdf" });

describe("files", () => {
  it("keeps Upload disabled until the notice is ticked, then sends acknowledged_notice", async () => {
    mockFetch(base(["edit_content"]));
    renderRoute(FILES);
    const u = userEvent.setup();
    await openDialog(u);
    expect(
      screen.getByText(
        "Do not upload participant identifiers. Upload only anonymized or aggregate data.",
      ),
    ).toBeInTheDocument();
    await u.upload(screen.getByLabelText("Choose file"), pdf());
    const btn = screen.getByRole("button", { name: "Upload" });
    expect(btn).toBeDisabled();
    await u.click(screen.getByRole("checkbox", { name: /no participant identifiers/i }));
    expect(btn).toBeEnabled();
    await u.click(btn);
    await waitFor(() => expect(FakeXHR.sent).toHaveLength(1));
    expect(FakeXHR.sent[0]!.get("acknowledged_notice")).toBe("true");
    expect((FakeXHR.sent[0]!.get("file") as File).name).toBe("n.pdf");
  });

  it("shows the notice unticked again on a second upload", async () => {
    mockFetch(base(["edit_content"]));
    renderRoute(FILES);
    const u = userEvent.setup();
    await openDialog(u);
    await u.click(screen.getByRole("checkbox"));
    await u.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await openDialog(u);
    expect(screen.getByText(/Do not upload participant identifiers/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
  });

  it("rejects oversize files client-side", async () => {
    mockFetch(base(["edit_content"]));
    renderRoute(FILES);
    const u = userEvent.setup();
    await openDialog(u);
    const big = new File(["x"], "big.bin");
    Object.defineProperty(big, "size", { value: 51 * 1024 * 1024 });
    await u.upload(screen.getByLabelText("Choose file"), big);
    expect(await screen.findByText(/The limit is 50 MB/)).toBeInTheDocument();
    await u.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
  });

  it("deletes a file only after the confirmation dialog", async () => {
    const calls = mockFetch({
      ...base(["edit_content"], [att]),
      "DELETE /api/labs/lab1/attachments/a1/": { body: {} },
    });
    renderRoute(FILES);
    await userEvent.click(await screen.findByRole("button", { name: /delete paper/i }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(await screen.findByRole("button", { name: "Delete file" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("hides upload and delete without edit_content", async () => {
    mockFetch(base(["view_project"], [att]));
    renderRoute(FILES);
    expect(await screen.findByRole("cell", { name: "paper.pdf" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete paper/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /upload file/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /download paper/i })).toHaveAttribute(
      "href",
      "/api/labs/lab1/attachments/a1/download/",
    );
  });

  it("lists documents and files together, and an old /files address lands there", async () => {
    const doc = {
      id: "d1",
      title: "Protocol",
      folder: null,
      updated_by: user,
      updated_at: "2026-02-01T00:00:00Z",
    };
    mockFetch({
      ...base(["view_project"], [att]),
      "GET /api/labs/lab1/projects/p1/documents/": { body: [doc] },
    });
    const router = renderRoute(FILES);
    expect(await screen.findByRole("cell", { name: "Protocol" })).toBeInTheDocument();
    expect(await screen.findByRole("cell", { name: "paper.pdf" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/labs/lab1/projects/p1/documents");
    // The PDF viewer keeps its own address: it must not resolve against /documents.
    expect(screen.getByRole("link", { name: "Open paper.pdf" })).toHaveAttribute(
      "href",
      `${FILES}/a1`,
    );
  });

  it("viewer requests the authenticated download endpoint", async () => {
    const calls = mockFetch({
      ...base(["view_project"]),
      "GET /api/labs/lab1/attachments/a1/download/": { body: null },
    });
    renderRoute(`${FILES}/a1`);
    expect(await screen.findByText("Page 1 of 3")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/labs/lab1/attachments/a1/download/")).toBe(true);
  });
});
