import { renderHook, screen, waitFor, within } from "@testing-library/react";
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

describe("adding results", () => {
  const NEW = "/labs/lab1/projects/p1/workflow/analysis/results/new";
  const edit = ["view_project", "edit_content"];

  it("offers one at a time or a full set, one at a time first", async () => {
    mockFetch(base(edit));
    renderRoute(NEW);
    expect(await screen.findByRole("button", { name: "One at a time" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(await screen.findByLabelText("Analysis that produced it")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "A full set at once" }));
    expect(await screen.findByLabelText("Analysis that produced them")).toBeInTheDocument();
  });

  it("asks for an analysis and at least one result before saving a set", async () => {
    const calls = mockFetch(base(edit));
    renderRoute(NEW);
    await userEvent.click(await screen.findByRole("button", { name: "A full set at once" }));
    await userEvent.click(screen.getByRole("button", { name: "Save all" }));
    expect(await screen.findByText(/Choose the analysis/)).toBeInTheDocument();
    expect(screen.getByText("Add at least one result")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("saves every row of a set in one request", async () => {
    const calls = mockFetch(base(edit, { [`POST ${P}/results/set/`]: { status: 201, body: [] } }));
    const router = renderRoute(NEW);
    await userEvent.click(await screen.findByRole("button", { name: "A full set at once" }));
    const picker = await screen.findByLabelText("Analysis that produced them");
    await screen.findByRole("option", { name: "Alpha diversity" });
    await userEvent.selectOptions(picker, "a1");
    const add = screen.getByRole("button", { name: "Add a result without a file" });
    await userEvent.click(add);
    await userEvent.click(add);
    await userEvent.type(screen.getByLabelText("Title of result 1"), "Figure 1");
    await userEvent.type(screen.getByLabelText("Title of result 2"), "Figure 2");
    await userEvent.click(screen.getByRole("button", { name: "Save all" }));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/labs/lab1/projects/p1/workflow/analysis"),
    );
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      analysis: "a1",
      items: [
        { title: "Figure 1", summary: "", attachments: [] },
        { title: "Figure 2", summary: "", attachments: [] },
      ],
    });
  });

  it("turns each uploaded figure into its own titled row", async () => {
    const sent: FormData[] = [];
    class FakeXHR {
      upload = {};
      status = 201;
      responseText = "";
      onload?: () => void;
      open() {}
      setRequestHeader() {}
      send(f: FormData) {
        sent.push(f);
        const name = (f.get("file") as File).name;
        this.responseText = JSON.stringify({ id: name, original_filename: name });
        queueMicrotask(() => this.onload?.());
      }
    }
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
    document.cookie = "csrftoken=t";
    mockFetch(base(edit));
    renderRoute(NEW);
    await userEvent.click(await screen.findByRole("button", { name: "A full set at once" }));
    await userEvent.click(await screen.findByRole("button", { name: "Upload figures" }));
    await userEvent.upload(await screen.findByLabelText("Choose file"), [
      new File(["a"], "fig1.png", { type: "image/png" }),
      new File(["b"], "fig2.final.png", { type: "image/png" }),
    ]);
    await userEvent.click(screen.getByRole("checkbox", { name: /no participant identifiers/i }));
    await userEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByLabelText("Title of result 2")).toHaveValue("fig2.final");
    expect(screen.getByLabelText("Title of result 1")).toHaveValue("fig1");
    expect(sent).toHaveLength(2);
    vi.unstubAllGlobals();
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
    renderRoute("/labs/lab1/projects/p1/workflow/data");
    expect(
      await screen.findByText(
        "A dataset record points to where data lives. We never store the data itself.",
      ),
    ).toBeInTheDocument();
  });

  it("shows analysis datasets with versions as links", async () => {
    mockFetch(base(["view_project"]));
    renderRoute("/labs/lab1/projects/p1/workflow/analysis/analyses/a1");
    const link = await screen.findByRole("link", { name: "Stool (v2)" });
    expect(link).toHaveAttribute("href", "/labs/lab1/projects/p1/workflow/data/datasets/d1");
    expect(screen.getByRole("link", { name: "View in lineage" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p1/workflow/lineage?focus=analysis:a1",
    );
  });

  it("hides export without permission", async () => {
    mockFetch(base(["view_project"]));
    renderRoute("/labs/lab1/projects/p1/workflow/analysis");
    await screen.findByText("Alpha diversity");
    expect(screen.queryByRole("button", { name: "Export project" })).not.toBeInTheDocument();
  });

  it("exports and downloads with permission", async () => {
    const calls = mockFetch(
      base(["view_project", "export"], { [`POST ${P}/export/`]: { body: { exported_at: "now" } } }),
    );
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderRoute("/labs/lab1/projects/p1/workflow/analysis");
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
      expect(labels).toContain("Go to project Gut study");
    });
  });
});

describe("Decision references form (D95)", () => {
  const decision = {
    id: "dc1",
    project: "p1",
    title: "Use rarefaction",
    rationale: "",
    decided_on: "2026-03-01",
    decided_by: user,
    supporting_documents: [],
    supporting_attachments: [],
    references: [{ title: "Old paper", url: "https://example.org/old", doi: "10.1234/old" }],
    analyses: [],
    results: [],
    datasets: [],
    created_at: "2026-03-01T00:00:00Z",
    updated_at: "2026-03-01T00:00:00Z",
  };

  it("shows safe links on the detail panel and saves edited references", async () => {
    const calls = mockFetch(
      base(["view_project", "edit_content"], {
        [`GET ${P}/decisions/`]: { body: [decision] },
        "GET /api/labs/lab1/decisions/dc1/": { body: decision },
        "PATCH /api/labs/lab1/decisions/dc1/": { body: decision },
      }),
    );
    renderRoute("/labs/lab1/projects/p1/workflow/review/decisions/dc1");
    expect(await screen.findByRole("link", { name: "Old paper" })).toHaveAttribute(
      "href",
      "https://example.org/old",
    );
    expect(screen.getByRole("link", { name: "DOI 10.1234/old" })).toHaveAttribute(
      "href",
      "https://doi.org/10.1234/old",
    );
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    await userEvent.click(await screen.findByRole("button", { name: "Add a reference" }));
    const row = screen.getByRole("group", { name: "Reference 2" });
    await userEvent.type(within(row).getByLabelText("DOI"), "bad");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findAllByText("Enter a title")).not.toHaveLength(0);
    expect(calls.some((c) => c.method === "PATCH")).toBe(false); // blocked client-side
    await userEvent.type(within(row).getByLabelText("Title"), "New one");
    await userEvent.clear(within(row).getByLabelText("DOI"));
    await userEvent.click(screen.getByRole("button", { name: "Move reference 2 up" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    const sent = calls.find((c) => c.method === "PATCH")!.body as {
      references: { title: string; url: string; doi: string }[];
    };
    expect(sent.references).toEqual([
      { title: "New one", url: "", doi: "" },
      { title: "Old paper", url: "https://example.org/old", doi: "10.1234/old" },
    ]);
  });
});
