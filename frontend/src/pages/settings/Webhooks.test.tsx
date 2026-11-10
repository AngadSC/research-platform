import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const PAGE = "/labs/lab1/settings/integrations";
const EVENTS = [{ value: "project.created", label: "A project was created" }];
const base = (perms: string[]) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(perms)] },
  "GET /api/labs/lab1/": { body: makeLab(perms) },
  "GET /api/labs/lab1/projects/": { body: [] },
  "GET /api/labs/lab1/notifications/": { body: [] },
  "GET /api/labs/lab1/integrations/providers/": { body: [] },
  "GET /api/labs/lab1/integrations/accounts/?all=true": { body: [] },
  "GET /api/labs/lab1/webhooks/": { body: { events: EVENTS, webhooks: [] } },
});
const MEMBER = ["view_lab", "manage_integrations"];
const ADMIN = [...MEMBER, "manage_lab_integrations"];

afterEach(() => vi.unstubAllGlobals());

describe("Automation webhooks", () => {
  it("are hidden from people who are not lab admins", async () => {
    mockFetch(base(MEMBER));
    renderRoute(PAGE);
    await screen.findByText("Services");
    expect(screen.queryByText("Automation")).toBeNull();
  });

  it("are added with chosen events, and the secret is shown once", async () => {
    const calls = mockFetch({
      ...base(ADMIN),
      "POST /api/labs/lab1/webhooks/": {
        status: 201,
        body: { id: "w1", name: "Zap", kind: "webhook", host: "h", events: [], secret: "S3CRET" },
      },
    });
    const user = userEvent.setup();
    renderRoute(PAGE);
    await user.click(await screen.findByRole("button", { name: "Add webhook" }));
    await user.type(screen.getByLabelText("Name"), "Zap");
    await user.type(screen.getByLabelText("Address"), "https://hooks.example.org/x");
    await user.click(screen.getByLabelText("A project was created"));
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect((await screen.findByLabelText("Signing secret")).getAttribute("value")).toBe("S3CRET");
    const post = calls.find((c) => c.method === "POST" && c.path.endsWith("/webhooks/"));
    expect(post?.body).toMatchObject({
      name: "Zap",
      kind: "webhook",
      url: "https://hooks.example.org/x",
      events: ["project.created"],
    });
  });
});
