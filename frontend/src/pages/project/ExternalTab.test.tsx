import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ASSISTANT_PREFILL } from "@/lib/assistant";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const P = "/api/labs/lab1/projects/p1";
const project = (perms: string[]) => ({
  id: "p1",
  name: "Gut study",
  status: "active",
  description: "",
  my_permissions: perms,
});
const item = {
  id: "x1",
  project: "p1",
  title: "SfN poster",
  type: "poster",
  date: "2030-05-01",
  place: "Halifax",
  url: "https://example.org/sfn",
  attachment: { id: "a1", original_filename: "poster.pdf", content_type: "x", size_bytes: 1 },
  created_by: user,
};
const base = (perms: string[], extra: Record<string, unknown> = {}) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  "GET /api/labs/lab1/projects/": { body: [project(perms)] },
  [`GET ${P}/`]: { body: project(perms) },
  [`GET ${P}/documents/`]: { body: [] },
  [`GET ${P}/attachments/`]: { body: [] },
  ...extra,
});
const PATH = "/labs/lab1/projects/p1/external";

const config = (can_use: boolean, has_key: boolean, ai_policy = "assistant") => ({
  [`GET /api/labs/lab1/assistant/config/`]: {
    body: { can_use, ai_policy, providers: [{ provider: "anthropic", has_key, models: [] }] },
  },
});

describe("conference suggestions", () => {
  it.each([
    ["the AI policy forbids it", config(false, true, "off")],
    ["there is no key", config(true, false)],
  ])("are hidden when %s", async (_why, extra) => {
    mockFetch(base(["view_project"], { [`GET ${P}/external/`]: { body: [] }, ...extra }));
    renderRoute(PATH);
    expect(await screen.findByText("No posters or talks yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Suggest conferences" })).toBeNull();
  });

  it("open the assistant with a question that is not sent", async () => {
    const calls = mockFetch(
      base(["view_project"], { [`GET ${P}/external/`]: { body: [] }, ...config(true, true) }),
    );
    const prefilled: string[] = [];
    const listen = (e: Event) => prefilled.push((e as CustomEvent<string>).detail);
    window.addEventListener(ASSISTANT_PREFILL, listen);
    renderRoute(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Suggest conferences" }));
    window.removeEventListener(ASSISTANT_PREFILL, listen);
    expect(prefilled[0]).toMatch(/Suggestions to verify/);
    expect(prefilled[0]).toMatch(/Do not add anything/);
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });
});

describe("External tab", () => {
  it("shows records with the file through the checked download endpoint", async () => {
    mockFetch(base(["view_project"], { [`GET ${P}/external/`]: { body: [item] } }));
    renderRoute(PATH);
    expect(await screen.findByText("SfN poster")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download poster.pdf" })).toHaveAttribute(
      "href",
      "/api/labs/lab1/attachments/a1/download/",
    );
    expect(screen.queryByRole("button", { name: "Add item" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Remove/ })).toBeNull();
  });

  it("checks the form, then saves a new record", async () => {
    const calls = mockFetch(
      base(["view_project", "edit_content"], {
        [`GET ${P}/external/`]: { body: [] },
        [`POST ${P}/external/`]: { status: 201, body: item },
      }),
    );
    renderRoute(PATH);
    await userEvent.click(await screen.findByRole("button", { name: "Add item" }));
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));
    expect(await screen.findByText("Enter a title")).toBeInTheDocument();
    expect(screen.getByText("Pick the date")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);

    await userEvent.type(screen.getByLabelText("Title"), "CNS talk");
    await userEvent.selectOptions(screen.getByLabelText("Type"), "presentation");
    await userEvent.type(screen.getByLabelText("Date"), "2030-06-01");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      title: "CNS talk",
      type: "presentation",
      date: "2030-06-01",
      place: "",
      url: "",
      attachment: null,
    });
  });
});
