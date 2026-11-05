import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExternalLinkItem } from "@/components/shared/ExternalLinkItem";
import type { ExternalLink } from "@/lib/api-types";
import { linkState } from "@/lib/integrations";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const PAGE = "/labs/lab1/settings/integrations";
const provider = (over: Record<string, unknown> = {}) => ({
  name: "google_drive",
  label: "Google Drive",
  auth_type: "oauth2",
  icon: "google-drive",
  scopes: ["drive.file"],
  configured: true,
  account: null,
  ...over,
});
const account = (over: Record<string, unknown> = {}) => ({
  id: "a1",
  provider: "google_drive",
  user,
  external_email: "ada@gmail.test",
  granted_scopes: [],
  status: "active",
  connected_at: "2026-01-01T00:00:00Z",
  last_used_at: null,
  ...over,
});
const base = (perms: string[], providers: unknown, accounts: unknown = []) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(perms)] },
  "GET /api/labs/lab1/": { body: makeLab(perms) },
  "GET /api/labs/lab1/projects/": { body: [] },
  "GET /api/labs/lab1/notifications/": { body: [] },
  "GET /api/labs/lab1/integrations/providers/": { body: providers },
  "GET /api/labs/lab1/integrations/accounts/?all=true": { body: accounts },
});
const MEMBER = ["view_lab", "manage_integrations"];
const ADMIN = [...MEMBER, "manage_lab_integrations"];

afterEach(() => vi.unstubAllGlobals());

describe("Integrations page", () => {
  it("offers Connect for a service that is not connected", async () => {
    const calls = mockFetch({
      ...base(MEMBER, [provider()]),
      "POST /api/labs/lab1/integrations/google_drive/connect/": {
        body: { authorization_url: "https://accounts.example/consent" },
      },
    });
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    renderRoute(PAGE);
    expect(await screen.findByText("Not connected")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Connect Google Drive" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://accounts.example/consent"));
    expect(calls.some((c) => c.method === "POST")).toBe(true);
  });

  it("shows a skeleton while loading, then an empty state with no services", async () => {
    mockFetch(base(MEMBER, []));
    renderRoute(PAGE);
    expect(await screen.findByText("No services yet")).toBeInTheDocument();
  });

  it("says when a service is not set up", async () => {
    mockFetch(base(MEMBER, [provider({ configured: false })]));
    renderRoute(PAGE);
    expect(await screen.findByText("Not set up for your institution")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Connect/ })).toBeNull();
  });

  it("disconnects your own account after a confirmation", async () => {
    const calls = mockFetch({
      ...base(MEMBER, [
        provider({ account: { id: "a1", status: "active", external_email: "ada@gmail.test" } }),
      ]),
      "DELETE /api/labs/lab1/integrations/accounts/a1/": { body: account({ status: "revoked" }) },
    });
    renderRoute(PAGE);
    await userEvent.click(await screen.findByRole("button", { name: "Disconnect Google Drive" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it.each(["expired", "revoked", "error"])("offers Reconnect when the account is %s", async (s) => {
    mockFetch(
      base(MEMBER, [provider({ account: { id: "a1", status: s, external_email: "x@y.test" } })]),
    );
    renderRoute(PAGE);
    expect(await screen.findByRole("button", { name: "Reconnect Google Drive" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /^Disconnect/ })).toBeNull();
  });

  it("shows a readable message when the server sends an error code back", async () => {
    mockFetch(base(MEMBER, [provider()]));
    renderRoute(`${PAGE}?error=other_account_connected`);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Another account is already connected. Disconnect it first.",
    );
  });

  it("lets a PI revoke someone else's connection", async () => {
    const other = account({
      id: "a2",
      user: { id: "u2", email: "bo@uni.edu", display_name: "Bo" },
    });
    const calls = mockFetch({
      ...base(ADMIN, [provider()], [other]),
      "DELETE /api/labs/lab1/integrations/accounts/a2/": {
        body: account({ id: "a2", status: "revoked" }),
      },
    });
    renderRoute(PAGE);
    expect(await screen.findByText("Everyone's connections")).toBeInTheDocument();
    await userEvent.click(
      await screen.findByRole("button", { name: "Revoke Bo's Google Drive connection" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("hides everyone's connections from a member", async () => {
    const calls = mockFetch(base(MEMBER, [provider()]));
    renderRoute(PAGE);
    await screen.findByText("Not connected");
    expect(screen.queryByText("Everyone's connections")).toBeNull();
    expect(calls.some((c) => c.path.includes("all=true"))).toBe(false);
  });
});

const link = (over: Partial<ExternalLink> = {}): ExternalLink =>
  ({
    id: "l1",
    project: "p1",
    provider: "google_drive",
    provider_label: "Google Drive",
    external_id: "f1",
    url: "https://drive.example/f1",
    title: "Raw data.csv",
    mime_type: "text/csv",
    linked_by: user,
    linked_modified_at: "2026-01-01T00:00:00Z",
    remote_modified_at: "2026-01-02T00:00:00Z",
    last_checked_at: null,
    unavailable_since: null,
    changed_since_linked: false,
    linker_connection_status: "active",
    created_at: "2026-01-01T00:00:00Z",
    ...over,
  }) as ExternalLink;

describe("ExternalLinkItem", () => {
  beforeEach(() => vi.useRealTimers());

  it("shows the title as a link, the provider, who linked it and a status", () => {
    render(
      <ul>
        <ExternalLinkItem link={link()} />
      </ul>,
    );
    const a = screen.getByRole("link", { name: /Raw data.csv/ });
    expect(a).toHaveAttribute("href", "https://drive.example/f1");
    expect(a).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getByText(/Linked by Ada/)).toBeInTheDocument();
    expect(screen.getByText("Up to date")).toBeInTheDocument();
  });

  it.each([
    [
      { unavailable_since: "2026-02-01T00:00:00Z", changed_since_linked: true },
      "No longer available",
    ],
    [{ changed_since_linked: true }, "Changed since linked"],
    [{ linker_connection_status: "revoked" }, "Can't check: the linker's connection is inactive"],
    [{ linker_connection_status: null }, "Up to date"],
  ] as [Partial<ExternalLink>, string][])("status for %j is %s", (over, text) => {
    expect(linkState(link(over)).label).toBe(text);
  });
});
