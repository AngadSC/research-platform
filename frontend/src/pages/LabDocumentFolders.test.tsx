import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const doc = (id: string, title: string, folder: string | null) => ({
  id,
  project: null,
  folder,
  title,
  kind: "doc",
  preview: { kind: "doc", text: `${title} text` },
  version: 1,
  updated_by: user,
  retain_until: null,
  retention_note: "",
  contains_participant_data: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  embed_url: "",
});
const folder = {
  id: "f1",
  project: null,
  parent: null,
  name: "SOPs",
  contains_participant_data: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("lab documents with folders", () => {
  it("shows the folder, filters by it and lists previews in the grid", async () => {
    mockFetch({
      [SESSION]: signedIn,
      "GET /api/labs/": { body: [makeLab(["view_lab", "contribute_lab"])] },
      "GET /api/labs/lab1/": { body: makeLab(["view_lab", "contribute_lab"]) },
      "GET /api/labs/lab1/lab-documents/": {
        body: [doc("d1", "Manual", null), doc("d2", "Cleaning", "f1")],
      },
      "GET /api/labs/lab1/lab-folders/": { body: [folder] },
      "GET /api/labs/lab1/start-here/": { body: [] },
    });
    renderRoute("/labs/lab1/documents?folder=f1");
    expect(await screen.findByText("Cleaning")).toBeInTheDocument();
    expect(screen.queryByText("Manual")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show as grid" }));
    expect(await screen.findByText("Cleaning text")).toBeInTheDocument();
  });
});
