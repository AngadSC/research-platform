import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.test", display_name: "Ada" };
const P = "/api/labs/lab1/projects/p1";
const project = {
  id: "p1",
  name: "Gut study",
  description: "",
  status: "active",
  created_by: user,
  my_project_role: "lead",
  my_permissions: ["view_project", "edit_content"],
};
const none = (kind: string) => [`GET ${P}/${kind}/`, { body: [] }] as const;
const csv = {
  id: "a1",
  project: "p1",
  original_filename: "data.csv",
  content_type: "text/csv",
  size_bytes: 10,
  sha256: "x",
  uploaded_by: user,
  created_at: "2026-01-01T00:00:00Z",
  drive_file_id: "",
  external_url: "",
  contains_participant_data: false,
};
const dataset = {
  id: "d1",
  name: "Stool",
  version_label: "v1",
  previous_version: null,
  data_file: { id: "a1", original_filename: "data.csv" },
  contains_participant_data: false,
  controlled_by: null,
};
const base = (files: unknown[] = [], datasets: unknown[] = []) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  "GET /api/labs/lab1/projects/": { body: [project] },
  [`GET ${P}/`]: { body: project },
  [`GET ${P}/datasets/`]: { body: datasets },
  [`GET ${P}/attachments/`]: { body: files },
  ...Object.fromEntries(
    ["documents", "analyses", "results", "decisions", "manuscripts", "folders"].map((k) => none(k)),
  ),
});

afterEach(() => vi.unstubAllGlobals());

describe("ways into the statistics page", () => {
  it("has Run statistics on the analyses list, even when it is empty", async () => {
    mockFetch(base());
    const router = renderRoute("/labs/lab1/projects/p1/workflow/analysis");
    await userEvent.click(await screen.findByRole("link", { name: /Run statistics/ }));
    expect(router.state.location.pathname).toBe("/labs/lab1/projects/p1/analyse");
  });

  it("has Analyse on a dataset row with a file", async () => {
    mockFetch(base([csv], [dataset]));
    const router = renderRoute("/labs/lab1/projects/p1/workflow/data");
    await userEvent.click(await screen.findByRole("link", { name: "Analyse Stool" }));
    expect(router.state.location.pathname).toBe("/labs/lab1/projects/p1/analyse");
    expect(router.state.location.search).toBe("?dataset=d1");
  });

  it("has Analyse in the menu of a CSV file, not of a PDF", async () => {
    mockFetch(
      base([
        csv,
        { ...csv, id: "a2", original_filename: "paper.pdf", content_type: "application/pdf" },
      ]),
    );
    const router = renderRoute("/labs/lab1/projects/p1/documents");
    const u = userEvent.setup();
    await u.click(await screen.findByRole("button", { name: "Actions for paper.pdf" }));
    expect(screen.queryByRole("menuitem", { name: "Analyse" })).toBeNull();
    await u.keyboard("{Escape}");
    await u.click(screen.getByRole("button", { name: "Actions for data.csv" }));
    await u.click(await screen.findByRole("menuitem", { name: "Analyse" }));
    expect(router.state.location.pathname).toBe("/labs/lab1/projects/p1/analyse");
    expect(router.state.location.search).toBe("?file=a1");
  });
});
