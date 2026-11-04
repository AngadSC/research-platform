import { renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useCommands } from "@/lib/commands";
import { validate } from "@/pages/project/ResearchForm";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

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
const P = "/api/labs/lab1/projects/p1";
const ds = { id: "d1", name: "Stool", version_label: "v2" };
const analysis = {
  id: "a1",
  project: "p1",
  title: "Alpha diversity",
  description: "",
  code_repo_url: "https://git.example/x",
  code_commit: "abc1234def",
  code_attachment: null,
  datasets: [ds],
  results: [],
  ran_by: user,
  ran_at: "2026-02-01T00:00:00Z",
};
const base = (perms: string[], extra: Record<string, unknown> = {}) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  "GET /api/labs/lab1/projects/": { body: [project(perms)] },
  [`GET ${P}/`]: { body: project(perms) },
  [`GET ${P}/documents/`]: { body: [] },
  [`GET ${P}/datasets/`]: { body: [] },
  [`GET ${P}/analyses/`]: { body: [analysis] },
  [`GET ${P}/results/`]: { body: [] },
  [`GET ${P}/decisions/`]: { body: [] },
  [`GET ${P}/manuscripts/`]: { body: [] },
  [`GET ${P}/members/`]: { body: [] },
  [`GET ${P}/attachments/`]: { body: [] },
  "GET /api/labs/lab1/analyses/a1/": { body: analysis },
  ...extra,
});

describe("research validation", () => {
  it("rejects a non-hex commit", () => {
    const e = validate("analyses", {
      title: "x",
      code_repo_url: "https://g.io/r",
      code_commit: "xyz1234",
    });
    expect(e.code_commit).toMatch(/0-9 and a-f/);
  });
  it("rejects a javascript: URL", () => {
    expect(validate("manuscripts", { title: "x", url: "javascript:alert(1)" }).url).toMatch(/http/);
    expect(
      validate("manuscripts", { title: "x", url: "https://www.overleaf.com/p" }).url,
    ).toBeUndefined();
  });
});

describe("Research tab", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("explains an empty list in plain words", async () => {
    mockFetch(base(["view_project"]));
    renderRoute("/labs/lab1/projects/p1/research/datasets");
    expect(
      await screen.findByText(
        "A dataset record points to where data lives. We never store the data itself.",
      ),
    ).toBeInTheDocument();
  });

  it("shows analysis datasets with versions as links", async () => {
    mockFetch(base(["view_project"]));
    renderRoute("/labs/lab1/projects/p1/research/analyses/a1");
    const link = await screen.findByRole("link", { name: "Stool (v2)" });
    expect(link).toHaveAttribute("href", "/labs/lab1/projects/p1/research/datasets/d1");
    expect(screen.getByRole("link", { name: "View in lineage" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p1/lineage?focus=analysis:a1",
    );
  });

  it("hides export without permission", async () => {
    mockFetch(base(["view_project"]));
    renderRoute("/labs/lab1/projects/p1/research/analyses");
    await screen.findByText("Alpha diversity");
    expect(screen.queryByRole("button", { name: "Export project" })).not.toBeInTheDocument();
  });

  it("exports and downloads with permission", async () => {
    const calls = mockFetch(
      base(["view_project", "export"], { [`POST ${P}/export/`]: { body: { exported_at: "now" } } }),
    );
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderRoute("/labs/lab1/projects/p1/research/analyses");
    await userEvent.click(await screen.findByRole("button", { name: "Export project" }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(calls.some((c) => c.method === "POST" && c.path === `${P}/export/`)).toBe(true);
    click.mockRestore();
  });

  it("registers palette commands for research records", async () => {
    mockFetch(base(["view_project", "edit_content"]));
    renderRoute("/labs/lab1/projects/p1/overview");
    const { result } = renderHook(() => useCommands());
    await waitFor(() => {
      const labels = result.current.map((c) => c.label);
      expect(labels).toContain("Analysis: Alpha diversity");
      expect(labels).toContain("New dataset");
      expect(labels).toContain("New analysis");
      expect(labels).toContain("Go to project: Gut study");
    });
  });
});
