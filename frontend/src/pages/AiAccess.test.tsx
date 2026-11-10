import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { oauthNav } from "@/hooks/ai";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const me = { id: "u1", email: "ada@uni.edu", display_name: "Ada", preferences: {} };
const lab2 = { ...makeLab(["view_lab"], "member"), id: "lab2", name: "Bio Lab" };
const app = {
  id: "g1",
  kind: "oauth",
  name: "Claude",
  client_name: "Claude",
  labs: [{ id: "lab1", name: "Ada Lab" }],
  access: "read",
  created_at: "2026-11-01T00:00:00Z",
  last_used_at: null,
  expires_at: null,
};
const token = { ...app, id: "g2", kind: "pat", name: "Laptop", client_name: "" };

const settings = (extra = {}) => ({
  [SESSION]: signedIn,
  "GET /api/me/": { body: me },
  "GET /api/labs/": { body: [makeLab(["view_lab", "manage_lab_integrations"]), lab2] },
  "GET /api/ai/grants/": { body: [app, token] },
  "GET /api/ai/keys/": { body: [] },
  "GET /api/labs/lab1/ai-policy/": { body: { ai_policy: "full" } },
  "GET /api/labs/lab1/ai-grants/": {
    body: [{ ...token, user: { id: "u2", display_name: "Grace", email: "g@uni.edu" } }],
  },
  ...extra,
});

describe("settings: AI access", () => {
  it("lists connected apps and tokens and revokes one", async () => {
    const calls = mockFetch(settings({ "DELETE /api/ai/grants/g1/": { status: 204 } }));
    renderRoute("/settings");
    const apps = await screen.findByRole("region", { name: "Connected AI apps" });
    expect(await within(apps).findByText("Claude")).toBeInTheDocument();
    expect(within(apps).getByText(/\/mcp$/)).toBeInTheDocument();
    const tokens = screen.getByRole("region", { name: "Access tokens" });
    expect(within(tokens).getByText("Laptop")).toBeInTheDocument();
    await userEvent.click(within(apps).getByRole("button", { name: "Revoke Claude" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("creates a token, shows it once with the Claude Code command, then hides it", async () => {
    const calls = mockFetch(
      settings({
        "POST /api/ai/grants/": {
          status: 201,
          body: { ...token, id: "g3", token: "rwp_secret123" },
        },
      }),
    );
    renderRoute("/settings");
    const form = await screen.findByRole("form", { name: "Create an access token" });
    await userEvent.type(within(form).getByLabelText("Token name"), "Claude Code");
    const create = within(form).getByRole("button", { name: "Create token" });
    expect(create).toBeDisabled(); // no lab chosen yet
    await userEvent.click(await within(form).findByRole("checkbox", { name: "Bio Lab" }));
    await userEvent.selectOptions(within(form).getByLabelText("Access"), "write");
    await userEvent.click(create);
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      name: "Claude Code",
      labs: ["lab2"],
      access: "write",
      expires_in_days: 30,
    });
    expect(await screen.findByLabelText("New access token")).toHaveTextContent("rwp_secret123");
    expect(screen.getByText(/claude mcp add --transport http/)).toHaveTextContent(
      "Authorization: Bearer rwp_secret123",
    );
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByText(/rwp_secret123/)).not.toBeInTheDocument();
  });

  it("asks for the password before creating a token, then retries once (D194)", async () => {
    let posts = 0;
    const calls = mockFetch(
      settings({
        "POST /api/ai/grants/": () => {
          posts += 1;
          return posts === 1
            ? { status: 401, body: { status: 401, data: { flows: [{ id: "reauthenticate" }] } } }
            : { status: 201, body: { ...token, id: "g3", token: "rwp_secret123" } };
        },
        "POST /_allauth/browser/v1/auth/reauthenticate": { body: { status: 200 } },
      }),
    );
    renderRoute("/settings");
    const form = await screen.findByRole("form", { name: "Create an access token" });
    await userEvent.type(within(form).getByLabelText("Token name"), "Claude Code");
    await userEvent.click(await within(form).findByRole("checkbox", { name: "Bio Lab" }));
    await userEvent.click(within(form).getByRole("button", { name: "Create token" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/password/i), "pw");
    await userEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    expect(await screen.findByLabelText("New access token")).toHaveTextContent("rwp_secret123");
    expect(posts).toBe(2);
    expect(calls.some((c) => c.path.endsWith("/auth/reauthenticate"))).toBe(true);
  });

  it("tells the owner why an AI connection was disconnected (D195)", async () => {
    const ended = {
      ...app,
      id: "g9",
      revoked_at: "2026-11-05T00:00:00Z",
      revoked_reason: "password_changed",
    };
    mockFetch(settings({ "GET /api/ai/grants/": { body: [ended, token] } }));
    renderRoute("/settings");
    const apps = await screen.findByRole("region", { name: "Connected AI apps" });
    expect(await within(apps).findByRole("status")).toHaveTextContent(
      /Claude stopped working because your password was changed/,
    );
    // it is a notice, not a connection: it has no Revoke button and is not counted as connected
    expect(within(apps).queryByRole("button", { name: /Revoke/ })).not.toBeInTheDocument();
    expect(within(apps).getByText("No AI apps connected.")).toBeInTheDocument();
  });

  it("shows each managed lab's AI access with Remove access, only for managers", async () => {
    mockFetch(settings({ "DELETE /api/labs/lab1/ai-grants/g2/": { status: 204 } }));
    renderRoute("/settings");
    const section = await screen.findByRole("region", { name: "AI access to Ada Lab" });
    expect(await within(section).findByText(/Grace/)).toBeInTheDocument();
    expect(within(section).getByRole("button", { name: "Remove access" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "AI access to Bio Lab" })).not.toBeInTheDocument();
  });
});

const QUERY =
  "?response_type=code&client_id=c1&redirect_uri=https%3A%2F%2Fclaude.ai%2Fapi%2Fmcp%2Fauth_callback" +
  "&code_challenge=abc&code_challenge_method=S256&state=xyz&scope=mcp%3Aread+mcp%3Awrite";

const checkReply = (client = {}) => ({
  client: {
    name: "Claude",
    verified_host: null,
    redirect_host: "claude.ai",
    loopback: false,
    ...client,
  },
  labs: [
    { id: "lab1", name: "Ada Lab", role: "pi" },
    { id: "lab2", name: "Bio Lab", role: "member" },
  ],
});

describe("OAuth consent page", () => {
  const base = {
    [SESSION]: signedIn,
    "GET /api/me/": { body: me },
    "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  };

  it("sends signed-out people to sign in and back", async () => {
    mockFetch({
      [SESSION]: { status: 401, body: { status: 401, data: { flows: [] }, meta: {} } },
    });
    const router = renderRoute(`/oauth/authorize${QUERY}`);
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(router.state.location.search).toContain(encodeURIComponent("/oauth/authorize?"));
  });

  it("shows the app, its redirect host and an unverified warning, then approves chosen labs", async () => {
    const go = vi.spyOn(oauthNav, "go").mockImplementation(() => {});
    const calls = mockFetch({
      ...base,
      "POST /api/oauth/authorize/": (req) =>
        (req.body as { decision: string }).decision === "check"
          ? { body: checkReply() }
          : { body: { redirect: "https://claude.ai/api/mcp/auth_callback?code=c&state=xyz" } },
    });
    renderRoute(`/oauth/authorize${QUERY}`);
    expect(await screen.findByRole("heading", { name: /Connect Claude to/ })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/Unverified app/); // prominent, not small print
    expect(screen.getByText("claude.ai")).toBeInTheDocument();
    // D198: the safest choice is the default: one lab, read only, even though write was asked for
    expect(screen.getByRole("checkbox", { name: /Ada Lab/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Bio Lab/ })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: /Read only/ })).toBeChecked();
    await userEvent.click(screen.getByRole("checkbox", { name: /Ada Lab/ }));
    const allow = screen.getByRole("button", { name: "Allow" });
    expect(allow).toBeDisabled(); // no lab ticked
    await userEvent.click(screen.getByRole("checkbox", { name: /Bio Lab/ }));
    await userEvent.click(allow);
    const approve = calls.filter((c) => c.method === "POST")[1]?.body as Record<string, unknown>;
    expect(approve).toMatchObject({
      decision: "approve",
      labs: ["lab2"],
      access: "read",
      client_id: "c1",
      code_challenge: "abc",
      state: "xyz",
    });
    await waitFor(() =>
      expect(go).toHaveBeenCalledWith("https://claude.ai/api/mcp/auth_callback?code=c&state=xyz"),
    );
    expect(allow).toBeDisabled(); // a second approval would replace the grant the app just got
  });

  it("warns before more than one lab or write access is granted", async () => {
    mockFetch({ ...base, "POST /api/oauth/authorize/": { body: checkReply() } });
    renderRoute(`/oauth/authorize${QUERY}`);
    await screen.findByRole("heading", { name: /Connect Claude to/ });
    expect(screen.queryByText(/You chose 2 labs/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: /Bio Lab/ }));
    expect(screen.getByText(/You chose 2 labs/)).toBeInTheDocument();
    expect(screen.queryByText(/able to add records as you/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Read and write/ }));
    expect(screen.getByText(/able to add records as you/)).toBeInTheDocument();
  });

  it("asks for the password when approving needs a recent check, then retries once (D194)", async () => {
    const go = vi.spyOn(oauthNav, "go").mockImplementation(() => {});
    let approvals = 0;
    const calls = mockFetch({
      ...base,
      "POST /api/oauth/authorize/": (req) => {
        if ((req.body as { decision: string }).decision === "check") return { body: checkReply() };
        approvals += 1;
        return approvals === 1
          ? { status: 401, body: { status: 401, data: { flows: [{ id: "reauthenticate" }] } } }
          : { body: { redirect: "https://claude.ai/cb?code=c" } };
      },
      "POST /_allauth/browser/v1/auth/reauthenticate": { body: { status: 200 } },
    });
    renderRoute(`/oauth/authorize${QUERY}`);
    await userEvent.click(await screen.findByRole("button", { name: "Allow" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/password/i), "pw");
    await userEvent.click(within(dialog).getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(go).toHaveBeenCalledWith("https://claude.ai/cb?code=c"));
    expect(approvals).toBe(2);
    expect(calls.some((c) => c.path.endsWith("/auth/reauthenticate"))).toBe(true);
  });

  it("warns about loopback apps and names a verified host", async () => {
    mockFetch({
      ...base,
      "POST /api/oauth/authorize/": {
        body: checkReply({
          verified_host: "claude.ai",
          loopback: true,
          redirect_host: "localhost",
        }),
      },
    });
    renderRoute(`/oauth/authorize${QUERY}`);
    expect(await screen.findByText("(identity published by claude.ai)")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("started this connection yourself");
  });

  it("denies", async () => {
    const go = vi.spyOn(oauthNav, "go").mockImplementation(() => {});
    mockFetch({
      ...base,
      "POST /api/oauth/authorize/": (req) =>
        (req.body as { decision: string }).decision === "check"
          ? { body: checkReply() }
          : { body: { redirect: "https://claude.ai/cb?error=access_denied" } },
    });
    renderRoute(`/oauth/authorize${QUERY}`);
    await userEvent.click(await screen.findByRole("button", { name: "Deny" }));
    await waitFor(() =>
      expect(go).toHaveBeenCalledWith("https://claude.ai/cb?error=access_denied"),
    );
  });

  it("explains an invalid request without redirecting anywhere", async () => {
    const go = vi.spyOn(oauthNav, "go").mockImplementation(() => {});
    mockFetch({
      ...base,
      "POST /api/oauth/authorize/": {
        status: 400,
        body: { error: "invalid_client", error_description: "Unknown app." },
      },
    });
    renderRoute(`/oauth/authorize${QUERY}`);
    expect(
      await screen.findByRole("heading", { name: "This connection request isn't valid" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Unknown app\./)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Return to the app" })).not.toBeInTheDocument();
    expect(go).not.toHaveBeenCalled();
  });
});
