import { cleanup, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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
const doc = (version: number, title = "Protocol") => ({
  id: "d1",
  project: "p1",
  folder: null,
  title,
  embed_url: "",
  embed_open_url: "",
  version,
  content: [],
  created_by: user,
  updated_by: user,
  retain_until: null,
  retention_note: "",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
});
const EDIT = ["view_project", "edit_content"];
const handlers = (d: unknown) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  "GET /api/labs/lab1/projects/p1/": { body: project(EDIT) },
  "GET /api/labs/lab1/projects/p1/folders/": { body: [] },
  "GET /api/labs/lab1/projects/p1/documents/": { body: [] },
  "GET /api/labs/lab1/documents/d1/": { body: d },
  "GET /api/labs/lab1/documents/d1/comments/": { body: [] },
  "GET /api/labs/lab1/projects/p1/members/": { body: [] },
});

describe("each kind of document opens in its own editor", () => {
  for (const [kind, content, find] of [
    ["doc", [], () => screen.findByRole("toolbar", { name: "Text formatting" })],
    [
      "sheet",
      [{ type: "sheet", sheets: [{ name: "Sheet1", cells: { A1: { text: "7" } } }] }],
      () => screen.findByRole("grid", { name: /Sheet1/ }),
    ],
    ["slides", [], () => screen.findByRole("group", { name: "Presentation" })],
  ] as const) {
    it(`kind ${kind}`, async () => {
      const err = vi.spyOn(console, "error");
      mockFetch(handlers({ ...doc(3), kind, content }));
      renderRoute("/labs/lab1/projects/p1/documents/d1");
      expect(await find()).toBeInTheDocument();
      cleanup();
      const bad = err.mock.calls.filter((c) =>
        /not a function|must not return/i.test(String(c[0])),
      );
      expect(bad).toEqual([]);
    });
  }
});
