import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LineageDetail } from "@/components/lineage/LineageDetail";
import type { LineageNode } from "@/lib/api-types";
import * as drive from "@/lib/drive";
import { indexLineage } from "@/lib/lineage";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

vi.mock("pdfjs-dist", () => ({ GlobalWorkerOptions: {}, getDocument: vi.fn() }));
// The Picker is stubbed: nothing here loads Google's script.
vi.mock("@/lib/drive", () => ({ pickDriveFile: vi.fn(), loadPicker: vi.fn() }));

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const project = {
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
  my_permissions: ["view_project", "edit_content"],
};
const provider = (over: Record<string, unknown> = {}) => ({
  name: "google_drive",
  label: "Google Drive",
  auth_type: "oauth2",
  icon: "google-drive",
  scopes: [],
  configured: true,
  public_config: { api_key: "pk", app_id: "123" },
  account: { id: "a1", status: "active", external_email: "ada@gmail.test" },
  ...over,
});
const link = (over: Record<string, unknown> = {}) => ({
  id: "l1",
  project: "p1",
  document: null,
  dataset: null,
  analysis: null,
  result: null,
  manuscript: null,
  provider: "google_drive",
  provider_label: "Google Drive",
  external_id: "f1",
  url: "https://drive.google.com/file/d/f1/view",
  title: "raw.csv",
  mime_type: "text/csv",
  linked_by: user,
  linked_modified_at: "2026-01-01T00:00:00Z",
  remote_modified_at: "2026-01-01T00:00:00Z",
  last_checked_at: null,
  unavailable_since: null,
  changed_since_linked: false,
  status: "ok",
  check_blocked: "",
  linker_connection_status: "active",
  created_at: "2026-01-01T00:00:00Z",
  ...over,
});
const LINKS = "GET /api/labs/lab1/projects/p1/external-links/";
const TOKEN = "GET /api/labs/lab1/integrations/google/picker-token/";
const token = { body: { access_token: "tok", expires_in: 3000, scope: "drive.file" } };
const base = (providers: unknown[], links: unknown[] = []) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  "GET /api/labs/lab1/projects/": { body: [project] },
  "GET /api/labs/lab1/projects/p1/": { body: project },
  "GET /api/labs/lab1/projects/p1/attachments/": { body: [] },
  "GET /api/labs/lab1/integrations/providers/": { body: providers },
  [LINKS]: { body: links },
});
const FILES = "/labs/lab1/projects/p1/files";
const LINK_BUTTON = { name: "Link from Google Drive" };

beforeEach(() => vi.mocked(drive.pickDriveFile).mockReset());
afterEach(() => vi.unstubAllGlobals());

describe("Google Drive on the Files tab", () => {
  it("hides the action when Drive is not set up", async () => {
    mockFetch(base([provider({ configured: false, public_config: {} })]));
    renderRoute(FILES);
    await screen.findByText("No files yet");
    expect(screen.queryByRole("button", LINK_BUTTON)).toBeNull();
  });

  it("hides the action when the Picker settings are missing", async () => {
    mockFetch(base([provider({ public_config: {} })]));
    renderRoute(FILES);
    await screen.findByText("No files yet");
    expect(screen.queryByRole("button", LINK_BUTTON)).toBeNull();
  });

  it("asks to connect first when there is no active account", async () => {
    const calls = mockFetch(base([provider({ account: null })]));
    renderRoute(FILES);
    await userEvent.click(await screen.findByRole("button", LINK_BUTTON));
    expect(drive.pickDriveFile).not.toHaveBeenCalled();
    expect(calls.some((c) => c.path.includes("picker-token"))).toBe(false);
  });

  it("gets a token, opens the Picker and links the picked file", async () => {
    vi.mocked(drive.pickDriveFile).mockResolvedValue({ id: "f1", name: "raw.csv" });
    const calls = mockFetch({
      ...base([provider()]),
      [TOKEN]: token,
      "POST /api/labs/lab1/projects/p1/external-links/": { status: 201, body: link() },
    });
    renderRoute(FILES);
    await userEvent.click(await screen.findByRole("button", LINK_BUTTON));
    await waitFor(() =>
      expect(drive.pickDriveFile).toHaveBeenCalledWith({
        apiKey: "pk",
        appId: "123",
        token: "tok",
      }),
    );
    await waitFor(() => {
      const post = calls.find((c) => c.method === "POST");
      expect(post?.body).toEqual({ provider: "google_drive", external_id: "f1" });
    });
  });

  it("does nothing more when the Picker is cancelled", async () => {
    vi.mocked(drive.pickDriveFile).mockResolvedValue(null);
    const calls = mockFetch({ ...base([provider()]), [TOKEN]: token });
    renderRoute(FILES);
    await userEvent.click(await screen.findByRole("button", LINK_BUTTON));
    await waitFor(() => expect(drive.pickDriveFile).toHaveBeenCalled());
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("shows a linked file that opens in a new tab, with the sharing note and its status", async () => {
    mockFetch(base([provider()], [link()]));
    renderRoute(FILES);
    const a = await screen.findByRole("link", { name: /raw.csv/ });
    expect(a).toHaveAttribute("href", "https://drive.google.com/file/d/f1/view");
    expect(a).toHaveAttribute("target", "_blank");
    expect(a).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(a).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
    expect(screen.getByText(/Opening this file uses Google's own sharing settings/)).toBeVisible();
    expect(screen.getByText(/Linked by Ada/)).toBeVisible();
    expect(screen.getByText("Up to date")).toBeVisible();
  });

  it("refreshes a link", async () => {
    const calls = mockFetch({
      ...base([provider()], [link()]),
      "POST /api/labs/lab1/external-links/l1/check/": { body: link() },
    });
    renderRoute(FILES);
    await userEvent.click(await screen.findByRole("button", { name: "Refresh raw.csv" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/check/"))).toBe(true));
  });

  it("offers Accept change when the file changed, and posts it", async () => {
    const calls = mockFetch({
      ...base([provider()], [link({ changed_since_linked: true, status: "changed" })]),
      "POST /api/labs/lab1/external-links/l1/accept-change/": { body: link() },
    });
    renderRoute(FILES);
    expect(await screen.findByText("Changed since linked")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Accept change to raw.csv" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/accept-change/"))).toBe(true));
  });

  it("says a deleted file is no longer available", async () => {
    const gone = link({ unavailable_since: "2026-02-01T00:00:00Z", status: "unavailable" });
    mockFetch(base([provider()], [gone]));
    renderRoute(FILES);
    expect(await screen.findByText("No longer available")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Accept change/ })).toBeNull();
  });

  it("says why a link can't be checked and hides Refresh", async () => {
    const blocked = link({ linker_connection_status: "expired", check_blocked: "linker_inactive" });
    mockFetch(base([provider()], [blocked]));
    renderRoute(FILES);
    expect(
      await screen.findByText(/Can't check: the linker's connection is inactive/),
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: "Refresh raw.csv" })).toBeNull();
  });

  it("asks for a relink when the linker lost access, and hides Refresh", async () => {
    mockFetch(base([provider()], [link({ check_blocked: "linker_access_lost" })]));
    renderRoute(FILES);
    expect(await screen.findByText(/lost access to this project. Relink it/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Refresh raw.csv" })).toBeNull();
  });

  it("never renders a blank or non-http link as a link", async () => {
    mockFetch(
      base(
        [provider()],
        [
          link({ id: "l2", title: "blanked", url: "" }),
          link({ id: "l3", title: "scripted", url: "javascript:alert(1)" }),
        ],
      ),
    );
    renderRoute(FILES);
    expect(await screen.findByText("blanked")).toBeVisible();
    expect(screen.queryByRole("link", { name: /blanked|scripted/ })).toBeNull();
    expect(screen.getByText("scripted")).toBeVisible();
  });

  it("keeps links to records off the project's file list", async () => {
    mockFetch(base([provider()], [link({ id: "l2", title: "in a dataset", dataset: "d1" })]));
    renderRoute(FILES);
    await screen.findByText("No files yet");
    expect(screen.queryByText("in a dataset")).toBeNull();
  });
});

describe("Drive link in the lineage panel", () => {
  it("shows the link and its status on the dataset node", () => {
    const node = {
      id: "dataset:d1",
      kind: "dataset",
      label: "Survey",
      subtitle: "v1",
      href_id: "d1",
      meta: {
        version_label: "v1",
        checksum: "md5:abc",
        external_links: [
          {
            id: "l1",
            provider: "google_drive",
            title: "raw.csv",
            url: "https://drive.google.com/file/d/f1/view",
            status: "changed",
          },
        ],
      },
    } as unknown as LineageNode;
    render(
      <MemoryRouter>
        <LineageDetail
          ix={indexLineage({ nodes: [node], edges: [] })}
          node={node}
          labId="lab1"
          projectId="p1"
          onSelect={() => {}}
          onClose={() => {}}
        />
      </MemoryRouter>,
    );
    expect(screen.getAllByText("raw.csv")[0]).toBeVisible();
    expect(screen.getAllByText("Changed since linked")[0]).toBeVisible();
  });
});
