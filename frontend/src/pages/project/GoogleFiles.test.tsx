import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as drive from "@/lib/drive";
import { googleEditor } from "@/lib/googleFiles";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: vi.fn(() => ({
    promise: Promise.resolve({
      numPages: 2,
      getPage: async () => ({
        getViewport: () => ({ width: 100, height: 100 }),
        render: () => ({ promise: Promise.resolve() }),
      }),
    }),
    destroy: vi.fn(),
  })),
}));
// The Picker is stubbed: nothing here loads Google's script.
vi.mock("@/lib/drive", async (orig) => ({
  ...(await orig<typeof import("@/lib/drive")>()),
  pickDriveFiles: vi.fn(),
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
const file = (over: Record<string, unknown>) => ({
  id: "a1",
  project: "p1",
  folder: null,
  original_filename: "paper.pdf",
  content_type: "application/pdf",
  size_bytes: 2048,
  sha256: "x",
  uploaded_by: user,
  notice_acknowledged_at: "2026-01-01T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
  drive_file_id: "",
  external_url: "",
  contains_participant_data: false,
  source: "web",
  ...over,
});
const gdoc = (id: string, name: string, kind: string, over = {}) =>
  file({
    id,
    original_filename: name,
    content_type: `application/vnd.google-apps.${kind}`,
    size_bytes: 0,
    drive_file_id: `drv-${id}`,
    external_url: `https://docs.google.com/x/d/drv-${id}/edit`,
    ...over,
  });
const drivePicker = {
  name: "google_drive",
  label: "Google Drive",
  auth_type: "oauth2",
  icon: "google_drive",
  category: "storage",
  scopes: [],
  link_targets: ["project"],
  link_methods: ["picker"],
  connect_fields: [],
  configured: true,
  public_config: { api_key: "pk", app_id: "123" },
  account: { id: "a1", status: "active", external_email: "ada@gmail.test" },
};
const base = (perms: string[], files: unknown[] = []) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  "GET /api/labs/lab1/projects/": { body: [project(perms)] },
  "GET /api/labs/lab1/projects/p1/": { body: project(perms) },
  "GET /api/labs/lab1/projects/p1/attachments/": { body: files },
  "GET /api/labs/lab1/projects/p1/documents/": { body: [] },
  "GET /api/labs/lab1/integrations/providers/": { body: [drivePicker] },
});
const DOCS = "/labs/lab1/projects/p1/documents";
const DOWNLOAD = (id: string) => `/api/labs/lab1/attachments/${id}/download/`;

class FakeXHR {
  static sent: FormData[] = [];
  upload = {};
  status = 201;
  responseText = JSON.stringify(file({}));
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

describe("googleEditor", () => {
  it("builds Google's own address for Docs, Sheets and Slides only", () => {
    const e = (content_type: string) => googleEditor({ content_type, drive_file_id: "a/b c" });
    expect(e("application/vnd.google-apps.document")?.edit).toBe(
      "https://docs.google.com/document/d/a%2Fb%20c/edit",
    );
    expect(e("application/vnd.google-apps.spreadsheet")?.preview).toBe(
      "https://docs.google.com/spreadsheets/d/a%2Fb%20c/preview",
    );
    expect(e("application/vnd.google-apps.presentation")?.label).toBe("Google Slides");
    expect(e("text/csv")).toBeNull();
    expect(
      googleEditor({ content_type: "application/vnd.google-apps.document", drive_file_id: "" }),
    ).toBeNull();
  });
});

describe("project files: one list", () => {
  it("shows uploads, Drive files and files made through Claude together, with participant badges", async () => {
    mockFetch(
      base(
        ["view_project"],
        [
          file({}),
          gdoc("g1", "Methods", "document"),
          file({
            id: "a3",
            original_filename: "fig.png",
            content_type: "image/png",
            source: "link",
          }),
          file({ id: "a4", original_filename: "raw.csv", contains_participant_data: true }),
        ],
      ),
    );
    renderRoute(DOCS);
    expect(await screen.findByRole("cell", { name: "Methods" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "paper.pdf" })).toBeInTheDocument();
    expect(screen.getByText("Google Docs")).toBeInTheDocument();
    expect(screen.getByText(/Image · .*added through Claude/)).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: /^raw\.csv/ })).toHaveTextContent(
      "Identifies participants",
    );
  });

  it("previews a PDF in a dialog through the download endpoint", async () => {
    const calls = mockFetch({
      ...base(["view_project"], [file({})]),
      [`GET ${DOWNLOAD("a1")}`]: { body: null },
    });
    renderRoute(DOCS);
    await userEvent.click(await screen.findByRole("button", { name: "Preview paper.pdf" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Page 1 of 2")).toBeInTheDocument();
    expect(calls.some((c) => c.path === DOWNLOAD("a1"))).toBe(true);
    expect(within(dialog).getByRole("link", { name: "Full page" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p1/files/a1",
    );
  });

  it("previews an image in a dialog from the download endpoint, not a public address", async () => {
    vi.stubGlobal(
      "URL",
      Object.assign(URL, { createObjectURL: () => "blob:img", revokeObjectURL: () => {} }),
    );
    const png = file({ id: "a2", original_filename: "fig.png", content_type: "image/png" });
    const calls = mockFetch({
      ...base(["view_project"], [png]),
      [`GET ${DOWNLOAD("a2")}`]: { body: "x" },
    });
    renderRoute(DOCS);
    await userEvent.click(await screen.findByRole("button", { name: "Preview fig.png" }));
    const img = await screen.findByRole("img", { name: "fig.png" });
    expect(img).toHaveAttribute("src", "blob:img");
    expect(calls.some((c) => c.path === DOWNLOAD("a2"))).toBe(true);
  });
});

describe("Google editor panel", () => {
  const files = [
    gdoc("g1", "Methods", "document"),
    gdoc("g2", "Counts", "spreadsheet"),
    gdoc("g3", "Talk", "presentation"),
  ];

  it("opens Edit in a docked panel with Open in Google and the sign-in note", async () => {
    mockFetch(base(["edit_content"], files));
    renderRoute(DOCS);
    await userEvent.click(await screen.findByRole("button", { name: "Edit Talk" }));
    const panel = await screen.findByRole("complementary", { name: /Talk in Google Slides/ });
    expect(within(panel).getByTitle("Talk")).toHaveAttribute(
      "src",
      "https://docs.google.com/presentation/d/drv-g3/edit",
    );
    const open = within(panel).getByRole("link", { name: /Open in Google/ });
    expect(open).toHaveAttribute("href", "https://docs.google.com/presentation/d/drv-g3/edit");
    expect(open).toHaveAttribute("target", "_blank");
    expect(
      within(panel).getByText(
        "If Google asks you to sign in, sign in to Google in this browser, or open it in a new tab.",
      ),
    ).toBeInTheDocument();
    // The list stays on screen beside it.
    expect(screen.getByRole("cell", { name: "Methods" })).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Close panel" }));
    expect(screen.queryByRole("complementary", { name: /Talk in/ })).toBeNull();
  });

  it("previews a Sheet in the same panel, and resizes it with the arrow keys", async () => {
    mockFetch(base(["edit_content"], files));
    renderRoute(DOCS);
    await userEvent.click(await screen.findByRole("button", { name: "Preview Counts" }));
    const panel = await screen.findByRole("complementary", { name: /Counts in Google Sheets/ });
    expect(within(panel).getByTitle("Counts")).toHaveAttribute(
      "src",
      "https://docs.google.com/spreadsheets/d/drv-g2/preview",
    );
    const handle = within(panel).getByRole("separator", { name: "Resize panel" });
    expect(handle).toHaveAttribute("aria-valuenow", "560");
    handle.focus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(handle).toHaveAttribute("aria-valuenow", "600");
  });

  it("offers Preview but not Edit to someone who cannot edit the project", async () => {
    mockFetch(base(["view_project"], files));
    renderRoute(DOCS);
    expect(await screen.findByRole("button", { name: "Preview Methods" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Edit / })).toBeNull();
  });

  it("does not offer Edit on a Drive file that is not a Doc, Sheet or Slides file", async () => {
    mockFetch(base(["edit_content"], [gdoc("g4", "raw", "x", { content_type: "text/csv" })]));
    renderRoute(DOCS);
    await screen.findByRole("cell", { name: "raw" });
    expect(screen.queryByRole("button", { name: "Edit raw" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Preview raw" })).toBeNull();
  });
});

describe("From Drive picks several files", () => {
  it("links every picked file and reports how many were added", async () => {
    vi.mocked(drive.pickDriveFiles).mockResolvedValue([
      { id: "f1", name: "one.csv" },
      { id: "f2", name: "two.csv" },
    ]);
    mockFetch({
      ...base(["edit_content"]),
      "GET /api/labs/lab1/integrations/google/picker-token/": {
        body: { access_token: "tok", expires_in: 3000, scope: "drive.file" },
      },
    });
    renderRoute(DOCS);
    await userEvent.click(await screen.findByRole("button", { name: "From Drive" }));
    await waitFor(() => expect(FakeXHR.sent).toHaveLength(2));
    expect(FakeXHR.sent.map((f) => f.get("drive_file_id"))).toEqual(["f1", "f2"]);
    expect(await screen.findByText("Added 2 files from Drive")).toBeInTheDocument();
  });
});

describe("Edit in Google (Word, Excel, PowerPoint)", () => {
  const word = file({ id: "w1", original_filename: "Draft.docx", content_type: "application/x" });
  const COPY = "POST /api/labs/lab1/attachments/w1/edit-in-google/";

  it("copies the file to Google and opens the copy in the editor panel", async () => {
    const calls = mockFetch({
      ...base(["edit_content"], [word]),
      [COPY]: {
        status: 201,
        body: gdoc("g9", "Draft", "document", { copied_from: "w1", folder: null }),
      },
    });
    renderRoute(DOCS);
    await userEvent.click(await screen.findByRole("button", { name: "Actions for Draft.docx" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Edit in Google" }));
    const panel = await screen.findByRole("complementary", { name: /Draft in Google Docs/ });
    expect(within(panel).getByTitle("Draft")).toHaveAttribute(
      "src",
      "https://docs.google.com/document/d/drv-g9/edit",
    );
    expect(calls.some((c) => `${c.method} ${c.path}` === COPY)).toBe(true);
  });

  it("shows the server's reason when the copy is refused", async () => {
    mockFetch({
      ...base(["edit_content"], [word]),
      [COPY]: {
        status: 400,
        body: { file: "Files marked as identifying participants stay in labbenchos." },
      },
    });
    renderRoute(DOCS);
    await userEvent.click(await screen.findByRole("button", { name: "Actions for Draft.docx" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Edit in Google" }));
    expect(
      await screen.findByText("Files marked as identifying participants stay in labbenchos."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: /in Google/ })).toBeNull();
  });

  it("is not offered to viewers or on other kinds of file", async () => {
    mockFetch(base(["view_project"], [word]));
    renderRoute(DOCS);
    await screen.findByRole("cell", { name: "Draft.docx" });
    await userEvent.click(screen.getByRole("button", { name: "Actions for Draft.docx" }));
    expect(screen.queryByRole("menuitem", { name: "Edit in Google" })).toBeNull();
  });
});

describe("documents table", () => {
  const word = file({
    id: "w1",
    original_filename: "Draft.docx",
    content_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size_bytes: 1331,
    contains_participant_data: true,
  });

  it("names the type plainly, puts the name before the badge and labels a Google copy", async () => {
    const copy = gdoc("g9", "Draft", "document", { copied_from: "w1" });
    mockFetch(
      base(
        ["edit_content"],
        [
          word,
          copy,
          file({ id: "c1", original_filename: "n.csv", content_type: "text/csv", size_bytes: 48 }),
        ],
      ),
    );
    renderRoute(DOCS);
    const cell = await screen.findByRole("cell", { name: /^Draft\.docx/ });
    expect(cell.textContent).toMatch(/^Draft\.docx.*Identifies participants/);
    expect(screen.getByText("Word · 1.3 KB")).toBeInTheDocument();
    expect(screen.getByText("CSV · 48 B")).toBeInTheDocument();
    expect(screen.getByText("Google copy of Draft.docx")).toBeInTheDocument();
  });

  it("downloads a file with no preview when its row is clicked", async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    mockFetch(
      base(
        ["edit_content"],
        [file({ id: "c1", original_filename: "n.csv", content_type: "text/csv" })],
      ),
    );
    renderRoute(DOCS);
    await userEvent.click(await screen.findByText("n.csv"));
    expect(click).toHaveBeenCalledTimes(1);
    click.mockRestore();
  });

  it("says a Drive file stays in Drive, and keeps the dialog open with the reason when delete fails", async () => {
    mockFetch({
      ...base(["edit_content"], [gdoc("g1", "Methods", "document")]),
      "DELETE /api/labs/lab1/attachments/g1/": { status: 502, body: { detail: "Bad gateway." } },
    });
    renderRoute(DOCS);
    await userEvent.click(await screen.findByRole("button", { name: "Actions for Methods" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));
    expect(await screen.findByText(/stays in your Google Drive/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete file" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete file" })).toBeInTheDocument();
  });
});
