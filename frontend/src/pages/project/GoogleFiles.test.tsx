import { act, screen, waitFor, within } from "@testing-library/react";
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
  window.innerWidth = 1920;
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

  it("stays open on other pages until its X is pressed (D326)", async () => {
    mockFetch({
      ...base(["edit_content"], files),
      "GET /api/labs/lab1/": { body: makeLab(["view_lab"]) },
      "GET /api/labs/lab1/chat/messages/": { body: [] },
      "POST /api/labs/lab1/chat/messages/read/": { status: 204 },
      "GET /api/labs/lab1/chat/google/": {
        body: { bridge: null, configured: false, connected: false, can_manage: false },
      },
    });
    const router = renderRoute(DOCS);
    await userEvent.click(await screen.findByRole("button", { name: "Edit Talk" }));
    const panel = await screen.findByRole("complementary", { name: /Talk in Google Slides/ });
    const frame = within(panel).getByTitle("Talk");
    await act(() => router.navigate("/labs/lab1/chat"));
    expect(await screen.findByRole("region", { name: "Lab chat" })).toBeInTheDocument();
    // The same frame, never reloaded: the person's place in the Doc is kept.
    const still = screen.getByRole("complementary", { name: /Talk in Google Slides/ });
    expect(within(still).getByTitle("Talk")).toBe(frame);
    await userEvent.click(within(still).getByRole("button", { name: "Close panel" }));
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
    expect(handle).toHaveAttribute("aria-valuenow", "584");
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
    // Asked once for the batch, as an upload asks (item 12 of the Google readiness report).
    await userEvent.click(await screen.findByLabelText(/no participant identifiers/));
    await userEvent.click(screen.getByRole("button", { name: "Link" }));
    await waitFor(() => expect(FakeXHR.sent).toHaveLength(2));
    expect(FakeXHR.sent.map((f) => f.get("drive_file_id"))).toEqual(["f1", "f2"]);
    expect(FakeXHR.sent.map((f) => f.get("contains_participant_data"))).toEqual(["false", "false"]);
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
        [file({ id: "c1", original_filename: "n.zip", content_type: "application/zip" })],
      ),
    );
    renderRoute(DOCS);
    await userEvent.click(await screen.findByText("n.zip"));
    expect(click).toHaveBeenCalledTimes(1);
    click.mockRestore();
  });

  it("opens a CSV in Analyse when its row is clicked", async () => {
    mockFetch(
      base(
        ["edit_content"],
        [file({ id: "c1", original_filename: "n.csv", content_type: "text/csv" })],
      ),
    );
    const router = renderRoute(DOCS);
    await userEvent.click(await screen.findByText("n.csv"));
    await waitFor(() => expect(router.state.location.search).toBe("?file=c1"));
    expect(router.state.location.pathname).toMatch(/\/analyse$/);
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

describe("Open in Overleaf", () => {
  const tex = file({ id: "t1", original_filename: "paper.tex", content_type: "text/x-tex" });
  const LINK = "POST /api/labs/lab1/attachments/t1/open-in-overleaf/";
  let posted: { action: string; fields: Record<string, string> } | undefined;

  beforeEach(() => {
    posted = undefined;
    vi.spyOn(window, "open").mockReturnValue(null);
    vi.spyOn(HTMLFormElement.prototype, "submit").mockImplementation(function (
      this: HTMLFormElement,
    ) {
      posted = {
        action: this.action,
        fields: Object.fromEntries(new FormData(this).entries()) as Record<string, string>,
      };
    });
  });

  it("posts the short-lived link to Overleaf's /docs address", async () => {
    mockFetch({
      ...base(["edit_content"], [tex]),
      [LINK]: { body: { url: "https://x.test/api/file-link?token=abc", name: "paper.tex" } },
    });
    renderRoute(DOCS);
    await userEvent.click(await screen.findByRole("button", { name: "Actions for paper.tex" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Open in Overleaf" }));
    await waitFor(() => expect(posted).toBeDefined());
    expect(posted?.action).toBe("https://www.overleaf.com/docs");
    expect(posted?.fields).toEqual({
      snip_uri: "https://x.test/api/file-link?token=abc",
      snip_name: "paper.tex",
    });
  });

  it("shows the server's reason and posts nothing when refused", async () => {
    mockFetch({
      ...base(["edit_content"], [tex]),
      [LINK]: {
        status: 400,
        body: { file: "This file identifies participants, so it cannot go to Overleaf." },
      },
    });
    renderRoute(DOCS);
    await userEvent.click(await screen.findByRole("button", { name: "Actions for paper.tex" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Open in Overleaf" }));
    expect(await screen.findByText(/cannot go to Overleaf/)).toBeInTheDocument();
    expect(posted).toBeUndefined();
  });

  it("is not offered to viewers or for other files", async () => {
    mockFetch(base(["view_project"], [tex]));
    renderRoute(DOCS);
    await screen.findByRole("cell", { name: "paper.tex" });
    await userEvent.click(screen.getByRole("button", { name: "Actions for paper.tex" }));
    expect(screen.queryByRole("menuitem", { name: "Open in Overleaf" })).toBeNull();
  });
});

describe("Edit in Word, Excel or PowerPoint (OneDrive)", () => {
  const word = file({ id: "w1", original_filename: "Draft.docx", content_type: "application/x" });
  const EDIT = "Files.ReadWrite.AppFolder";
  const onedrive = {
    ...drivePicker,
    name: "onedrive",
    label: "OneDrive and SharePoint",
    icon: "onedrive",
    scopes: ["Files.Read.All", "offline_access", EDIT],
    link_methods: ["search"],
    public_config: {},
    account: null,
  };
  const account = (scopes: string[]) => ({
    id: "od1",
    provider: "onedrive",
    user,
    external_email: "ada@example.test",
    instance_url: "",
    granted_scopes: scopes,
    status: "active",
    connected_at: "2026-01-01T00:00:00Z",
    last_used_at: null,
  });
  const routes = (accounts: unknown[], configured = true) => ({
    ...base(["edit_content"], [word]),
    "GET /api/labs/lab1/integrations/providers/": {
      body: [drivePicker, { ...onedrive, configured }],
    },
    "GET /api/labs/lab1/integrations/accounts/": { body: accounts },
  });
  const COPY = "POST /api/labs/lab1/attachments/w1/edit-in-office/";
  const CONNECT = "POST /api/labs/lab1/integrations/onedrive/connect/";
  const openMenu = async () => {
    renderRoute(DOCS);
    await userEvent.click(await screen.findByRole("button", { name: "Actions for Draft.docx" }));
  };

  it("copies the file to your OneDrive and offers to open it in Word", async () => {
    const calls = mockFetch({
      ...routes([account(["Files.Read.All", EDIT])]),
      [COPY]: {
        status: 201,
        body: file({
          id: "o9",
          original_filename: "Draft.docx",
          external_url: "https://contoso-my.sharepoint.com/x/Draft.docx",
          copied_from: "w1",
        }),
      },
    });
    await openMenu();
    await userEvent.click(await screen.findByRole("menuitem", { name: "Edit in Word" }));
    expect(await screen.findByText(/Copied to your OneDrive/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open in Word" })).toBeInTheDocument();
    expect(calls.some((c) => `${c.method} ${c.path}` === COPY)).toBe(true);
  });

  it("asks to allow editing first, and asks Microsoft for that permission only then", async () => {
    const calls = mockFetch({
      ...routes([account(["Files.Read.All"])]),
      [CONNECT]: { body: { authorization_url: "", account: null } },
    });
    await openMenu();
    await userEvent.click(await screen.findByRole("menuitem", { name: "Edit in Word" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit in Word" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Allow editing in Office" }));
    await waitFor(() =>
      expect(calls.find((c) => `${c.method} ${c.path}` === CONNECT)?.body).toEqual({
        scopes: ["Files.Read.All", "offline_access", EDIT],
      }),
    );
    expect(calls.some((c) => `${c.method} ${c.path}` === COPY)).toBe(false);
  });

  it("offers to connect OneDrive when it is not connected", async () => {
    mockFetch(routes([]));
    await openMenu();
    await userEvent.click(await screen.findByRole("menuitem", { name: "Edit in Word" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit in Word" });
    expect(within(dialog).getByRole("button", { name: "Connect OneDrive" })).toBeInTheDocument();
  });

  it("is not offered when the site has no OneDrive set up", async () => {
    mockFetch(routes([], false));
    await openMenu();
    expect(await screen.findByRole("menuitem", { name: "Edit in Google" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Edit in Word" })).toBeNull();
  });

  it("labels a OneDrive copy and offers no copy of the copy", async () => {
    const copy = file({
      id: "o9",
      original_filename: "Draft copy.docx",
      content_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      external_url: "https://contoso-my.sharepoint.com/x/Draft.docx",
      size_bytes: 0,
      copied_from: "w1",
    });
    mockFetch({
      ...routes([account([EDIT])]),
      "GET /api/labs/lab1/projects/p1/attachments/": { body: [word, copy] },
    });
    renderRoute(DOCS);
    expect(await screen.findByText("OneDrive copy of Draft.docx")).toBeInTheDocument();
    expect(screen.getByText("Word in OneDrive")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Actions for Draft copy.docx" }));
    expect(screen.queryByRole("menuitem", { name: "Edit in Word" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "Edit in Google" })).toBeNull();
  });
});
