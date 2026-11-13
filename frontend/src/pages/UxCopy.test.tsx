import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { activeFirst } from "@/pages/LabHomePage";
import { ProjectFormDialog } from "@/pages/project/ProjectFormDialog";
import { PROJECT_SECTIONS } from "@/lib/nav";
import type { Project } from "@/lib/api-types";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

afterEach(() => vi.unstubAllGlobals());

const proj = (name: string, status: string, at: string) =>
  ({ name, status, updated_at: at, last_activity_at: null }) as unknown as Project;

describe("Projects list order", () => {
  it("puts active projects first and archived last", () => {
    const rows = activeFirst([
      proj("Old", "archived", "2026-03-01T00:00:00Z"),
      proj("A", "active", "2026-01-01T00:00:00Z"),
      proj("B", "planning", "2026-02-01T00:00:00Z"),
    ]);
    expect(rows.map((p) => p.name)).toEqual(["B", "A", "Old"]);
  });
});

describe("Project sidebar labels", () => {
  it("calls the outside tab Posters and talks and explains Workflow", () => {
    expect(PROJECT_SECTIONS.map((s) => s.label)).toContain("Posters and talks");
    expect(PROJECT_SECTIONS.find((s) => s.to === "workflow")?.hint).toMatch(/ethics/);
  });
});

describe("New project dialog", () => {
  const open = (canRetention = true) =>
    render(
      <ProjectFormDialog
        open
        onOpenChange={() => {}}
        canRetention={canRetention}
        onSave={vi.fn()}
      />,
    );

  it("hides retention under More options, with a hint", () => {
    open();
    const more = screen.getByText("More options").closest("details")!;
    expect(more).not.toHaveAttribute("open");
    expect(within(more).getByLabelText("Keep until")).toBeInTheDocument();
    expect(within(more).getByText(/how long the lab must keep/)).toBeInTheDocument();
  });

  it("has no More options for people who cannot see retention", () => {
    open(false);
    expect(screen.queryByText("More options")).toBeNull();
  });

  it("shows what each template includes in the list", async () => {
    open();
    await userEvent.click(screen.getByRole("combobox", { name: "Start from" }));
    expect(await screen.findByText(/over about nine months/)).toBeVisible();
    expect(screen.getByText(/writing the survey to reporting results/)).toBeVisible();
    expect(screen.getByText(/working with existing data/)).toBeVisible();
  });
});

describe("Help and Settings", () => {
  const shell = {
    [SESSION]: signedIn,
    "GET /api/labs/": { body: [makeLab(["view_lab"])] },
    "GET /api/me/": {
      body: { id: "u1", email: "ada@uni.edu", display_name: "Ada", preferences: {} },
    },
    "GET /api/ai/grants/": { body: [] },
    "GET /api/ai/keys/": { body: [] },
  };

  it("Help has a Connect Claude section with the steps", async () => {
    mockFetch(shell);
    renderRoute("/help");
    const h = await screen.findByRole("heading", { name: "Connect Claude" });
    const section = h.closest("section")!;
    expect(within(section).getByText(/Click Add, then sign in/)).toBeVisible();
    expect(screen.getByText(/tell your lab admin/i)).toBeVisible();
  });

  it("Settings AI shows Connected AI apps before the API key forms", async () => {
    mockFetch(shell);
    renderRoute("/settings#ai");
    const apps = await screen.findByRole("heading", { name: "Connected AI apps" });
    const keys = await screen.findByRole("heading", { name: "Assistant API keys" });
    expect(apps.compareDocumentPosition(keys) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
