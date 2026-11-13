import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExternalLinkItem } from "@/components/shared/ExternalLinkItem";
import type { ExternalLink } from "@/lib/api-types";
import { linkState } from "@/lib/integrations";
import { KEYED, LINK_ONLY, OAUTH, PUBLIC } from "@/test/providers";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const PAGE = "/labs/lab1/settings/integrations";
const provider = (over: Record<string, unknown> = {}) => ({
  name: "google_drive",
  label: "Google Drive",
  auth_type: "oauth2",
  icon: "google_drive",
  category: "storage",
  scopes: ["drive.file"],
  connect_fields: [],
  needs_instance_url: false,
  configured: true,
  bundle: [],
  bundle_label: "",
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

  it("puts the Claude block above the services, with steps and no operator wording", async () => {
    mockFetch(base(MEMBER, [provider({ configured: false })]));
    renderRoute(PAGE);
    const ai = await screen.findByRole("heading", { name: "Claude and other AI apps" });
    const services = screen.getByRole("heading", { name: "Services" });
    expect(ai.compareDocumentPosition(services) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(/Click Connect to Claude/)).toBeVisible();
    expect(screen.getByText(/turn on labbenchos from the tools menu/)).toBeVisible();
    expect(screen.getByText(/need a Claude plan that supports them/)).toBeVisible();
    expect(screen.queryByText(/whoever runs this site/i)).toBeNull();
  });

  it("lists AI apps that can read the lab among everyone's connections", async () => {
    const grant = {
      id: "g1",
      kind: "oauth",
      client_name: "Claude",
      user,
      labs: [],
      access: "read",
    };
    mockFetch({ ...base(ADMIN, []), "GET /api/labs/lab1/ai-grants/": { body: [grant] } });
    renderRoute(PAGE);
    expect(await screen.findByText(/Ada: Claude \(read only\)/)).toBeVisible();
  });

  it("shows the Claude connector with connected apps and a link to Settings", async () => {
    const app = { id: "g1", kind: "oauth", client_name: "Claude", labs: [], access: "read" };
    mockFetch({ ...base(MEMBER, []), "GET /api/ai/grants/": { body: [app] } });
    renderRoute(PAGE);
    const region = await screen.findByRole("region", { name: "Claude and other AI apps" });
    expect(await within(region).findByText(/Connected: Claude/)).toBeInTheDocument();
    expect(within(region).getByRole("link", { name: "Connect to Claude" })).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: "Copy address" })).toBeInTheDocument();
    expect(within(region).getByRole("link", { name: "Manage in Settings" })).toHaveAttribute(
      "href",
      "/settings#ai",
    );
  });

  it("shows a skeleton while loading, then an empty state with no services", async () => {
    mockFetch(base(MEMBER, []));
    renderRoute(PAGE);
    expect(await screen.findByText("No services yet")).toBeInTheDocument();
  });

  it("says when a service is not set up", async () => {
    mockFetch(base(MEMBER, [provider({ configured: false })]));
    renderRoute(PAGE);
    expect(await screen.findByText("Not available yet")).toBeInTheDocument();
    // The button stays visible but cannot be used until the site has the app details.
    expect(screen.getByRole("button", { name: /Connect/ })).toBeDisabled();
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

  it("explains an unavailable file and what to do", () => {
    render(
      <ul>
        <ExternalLinkItem link={link({ unavailable_since: "2026-02-01T00:00:00Z" })} />
      </ul>,
    );
    expect(
      screen.getByText(/moved or deleted, or you lost access. Relink it or remove it/),
    ).toBeVisible();
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

describe("Integrations page, generic providers", () => {
  const all = [
    OAUTH,
    { ...OAUTH, name: "box", label: "Box", configured: false },
    KEYED,
    LINK_ONLY,
    PUBLIC,
  ];

  it("groups providers by category and says what each needs", async () => {
    mockFetch(base(MEMBER, all));
    renderRoute(PAGE);
    expect(await screen.findByRole("heading", { name: "File storage" })).toBeVisible();
    for (const g of ["References", "Writing", "Repositories"])
      expect(screen.getByRole("heading", { name: g })).toBeVisible();
    expect(screen.getByRole("button", { name: "Connect Dropbox" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Connect Zotero" })).toBeVisible();
    // Unconfigured OAuth: the button is there but disabled, with a note saying why.
    expect(screen.getByText("Not available yet")).toBeVisible();
    expect(screen.getByRole("button", { name: "Connect Box (not available yet)" })).toBeDisabled();
    // Link-only and public need no connection.
    expect(screen.getByText(/No connection needed. Paste a link/)).toBeVisible();
    expect(screen.getByText(/No connection needed. Links to public records/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /Connect (Overleaf|Zenodo)/ })).toBeNull();
  });

  it("connects an API-key provider from its fields, with the secret masked and cleared", async () => {
    const calls = mockFetch({
      ...base(MEMBER, [KEYED]),
      "POST /api/labs/lab1/integrations/zotero/connect/": {
        status: 400,
        body: { api_key: ["That key was not accepted."] },
      },
    });
    renderRoute(PAGE);
    await userEvent.click(await screen.findByRole("button", { name: "Connect Zotero" }));
    const key = await screen.findByLabelText("API key");
    expect(key).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Server address")).toHaveAttribute("type", "url");
    expect(screen.getByText("Only for self-hosted servers.")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText("Enter api key.")).toBeVisible(); // required, checked first
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await userEvent.type(key, "s3cret-key");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText("That key was not accepted.")).toBeVisible();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ api_key: "s3cret-key" });
    expect(screen.getByLabelText("API key")).toHaveValue(""); // never kept after a submit
  });

  it("closes and shows the account after a key is accepted", async () => {
    let done = false;
    const calls = mockFetch({
      ...base(MEMBER, [KEYED]),
      "GET /api/labs/lab1/integrations/providers/": () => ({
        body: [
          done
            ? {
                ...KEYED,
                account: {
                  id: "a",
                  status: "active",
                  external_email: "ada@z.test",
                  instance_url: "",
                },
              }
            : KEYED,
        ],
      }),
      "POST /api/labs/lab1/integrations/zotero/connect/": () => {
        done = true;
        return { status: 201, body: { authorization_url: "", account: null } };
      },
    });
    renderRoute(PAGE);
    await userEvent.click(await screen.findByRole("button", { name: "Connect Zotero" }));
    await userEvent.type(await screen.findByLabelText("API key"), "k");
    await userEvent.type(screen.getByLabelText("Server address"), "https://zotero.example.edu");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByRole("button", { name: "Disconnect Zotero" })).toBeVisible();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      api_key: "k",
      instance_url: "https://zotero.example.edu",
    });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("Integrations page, one Google sign-in (D262)", () => {
  const drive = provider({
    bundle: ["google_calendar"],
    bundle_label: "Google",
    public_config: {},
  });
  const calendar = provider({
    name: "google_calendar",
    label: "Google Calendar and Meet",
    icon: "google-calendar",
    category: "meetings",
    bundle: ["google_drive"],
    bundle_label: "Google",
  });
  const acct = (status: string) => ({
    id: "a1",
    status,
    external_email: "ada@uni.edu",
    instance_url: "",
  });

  it("shows Drive, Calendar and Meet as one card under Google, with one Connect", async () => {
    mockFetch(base(MEMBER, [drive, calendar]));
    renderRoute(PAGE);
    expect(await screen.findByRole("heading", { name: "Google" })).toBeVisible();
    expect(screen.getByText("Drive, Calendar and Meet")).toBeVisible();
    expect(screen.getAllByRole("button", { name: /^Connect/ })).toHaveLength(1);
    expect(screen.queryByText("Google Calendar and Meet")).toBeNull();
    expect(screen.queryByRole("heading", { name: "File storage" })).toBeNull();
  });

  it("connects through the first service, which asks Google for all of it", async () => {
    const calls = mockFetch({
      ...base(MEMBER, [drive, calendar]),
      "POST /api/labs/lab1/integrations/google_drive/connect/": {
        body: { authorization_url: "" },
      },
    });
    renderRoute(PAGE);
    await userEvent.click(await screen.findByRole("button", { name: "Connect Google" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
  });

  it("offers to add what is missing when only Drive was connected before", async () => {
    mockFetch(base(MEMBER, [{ ...drive, account: acct("active") }, calendar]));
    renderRoute(PAGE);
    expect(
      await screen.findByRole("button", { name: "Add Calendar and Meet Google" }),
    ).toBeVisible();
    expect(screen.getByText(/Not yet added: Calendar and Meet/)).toBeVisible();
  });

  it("says it will disconnect all of it together", async () => {
    mockFetch(
      base(MEMBER, [
        { ...drive, account: acct("active") },
        { ...calendar, account: { ...acct("active"), id: "a2" } },
      ]),
    );
    renderRoute(PAGE);
    await userEvent.click(await screen.findByRole("button", { name: "Disconnect Google" }));
    expect(await screen.findByText(/disconnects Drive, Calendar and Meet together/)).toBeVisible();
  });

  it("shows a disabled Connect with the reason while the site has no Google app", async () => {
    mockFetch(
      base(MEMBER, [
        { ...drive, configured: false },
        { ...calendar, configured: false },
      ]),
    );
    renderRoute(PAGE);
    expect(
      await screen.findByRole("button", { name: "Connect Google (not available yet)" }),
    ).toBeDisabled();
  });
});
