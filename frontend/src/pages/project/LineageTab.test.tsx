import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { COMMIT, sample } from "@/lib/lineage.fixture";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

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
  my_permissions: ["view_project"],
};
const handlers = (lineage: { status?: number; body?: unknown }) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  "GET /api/labs/lab1/projects/": { body: [project] },
  "GET /api/labs/lab1/projects/p1/": { body: project },
  "GET /api/labs/lab1/projects/p1/lineage/": lineage,
});
const PATH = "/labs/lab1/projects/p1/lineage";

beforeEach(() => {
  // React Flow measures nodes with these; happy-dom has neither.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal(
    "DOMMatrixReadOnly",
    class {
      m22 = 1;
      constructor() {}
    },
  );
});

describe("Lineage tab", () => {
  it("shows an empty state that points at datasets", async () => {
    mockFetch(handlers({ body: { nodes: [], edges: [] } }));
    renderRoute(PATH);
    expect(await screen.findByText("Add a dataset to start tracing your work")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add a dataset" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p1/research/datasets",
    );
  });

  it("shows a friendly message when loading fails", async () => {
    mockFetch(handlers({ status: 500, body: {} }));
    renderRoute(PATH);
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side");
  });

  it("lists every node in the list view", async () => {
    mockFetch(handlers({ body: sample }));
    renderRoute(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "List view" }));
    const list = within(screen.getByTestId("lineage-list"));
    for (const label of ["Gut paper", "Figure 1", "Figure 2", "Microbiome run", "Drop outliers"])
      expect(list.getByRole("button", { name: label })).toBeInTheDocument();
    expect(list.getAllByRole("button", { name: "Gut samples" })).toHaveLength(2);
  });

  it("opens the panel for a result with the producing commit and dataset versions", async () => {
    mockFetch(handlers({ body: sample }));
    renderRoute(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "List view" }));
    await userEvent.click(
      within(screen.getByTestId("lineage-list")).getByRole("button", { name: "Figure 1" }),
    );
    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByRole("heading", { name: "Upstream" })).toBeInTheDocument();
    expect(within(panel).getByText(COMMIT)).toBeInTheDocument();
    expect(within(panel).getByText("sha256-bbb")).toBeInTheDocument();
    expect(within(panel).getByText("sha256-aaa")).toBeInTheDocument();
    const repo = within(panel).getByRole("link", { name: /github.com\/lab\/gut/ });
    expect(repo).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(panel).getByRole("link", { name: "Open full record" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p1/research/results/r1",
    );
  });

  it("renders the canvas with a focusable button per item", async () => {
    mockFetch(handlers({ body: sample }));
    renderRoute(PATH);
    const node = await screen.findByRole("button", { name: "Result: Figure 1" });
    // happy-dom cannot run d3-zoom pointer handling, so click directly.
    fireEvent.click(node);
    expect(await screen.findByRole("dialog")).toHaveTextContent(COMMIT);
  });
});
