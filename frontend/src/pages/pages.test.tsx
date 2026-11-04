import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn, signedOut } from "@/test/utils";

const LOGIN_PATH = "/_allauth/browser/v1/auth/login";
const MFA_PATH = "/_allauth/browser/v1/auth/2fa/authenticate";

describe("login", () => {
  it("signs in and lands on the first-run empty state", async () => {
    let authed = false;
    const calls = mockFetch({
      [SESSION]: () => (authed ? signedIn : signedOut),
      [`POST ${LOGIN_PATH}`]: () => {
        authed = true;
        return signedIn;
      },
      "GET /api/labs/": { body: [] },
    });
    document.cookie = "csrftoken=t";
    renderRoute("/login");
    await userEvent.type(await screen.findByLabelText("Email"), "ada@uni.edu");
    await userEvent.type(screen.getByLabelText("Password"), "hunter2hunter2");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Create your first lab")).toBeInTheDocument();
    expect(calls.find((c) => c.path === LOGIN_PATH)?.body).toEqual({
      email: "ada@uni.edu",
      password: "hunter2hunter2",
    });
  });

  it("shows inline errors for empty fields", async () => {
    mockFetch({ [SESSION]: signedOut });
    renderRoute("/login");
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(screen.getByText("Enter your email address")).toBeInTheDocument();
    expect(screen.getByText("Enter your password")).toBeInTheDocument();
  });

  it("asks for a TOTP code when allauth reports a pending mfa_authenticate flow", async () => {
    let authed = false;
    const lab = makeLab(["view_lab"]);
    const calls = mockFetch({
      [SESSION]: () => (authed ? signedIn : signedOut),
      [`POST ${LOGIN_PATH}`]: {
        status: 401,
        body: {
          status: 401,
          data: { flows: [{ id: "login" }, { id: "mfa_authenticate", is_pending: true }] },
          meta: { is_authenticated: false },
        },
      },
      [`POST ${MFA_PATH}`]: () => {
        authed = true;
        return signedIn;
      },
      "GET /api/labs/": { body: [lab] },
      "GET /api/labs/lab1/": { body: lab },
    });
    document.cookie = "csrftoken=t";
    renderRoute("/login");
    await userEvent.type(await screen.findByLabelText("Email"), "ada@uni.edu");
    await userEvent.type(screen.getByLabelText("Password"), "pw");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await userEvent.type(await screen.findByLabelText("Authentication code"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    await waitFor(() => expect(calls.some((c) => c.path === MFA_PATH)).toBe(true));
    expect(calls.find((c) => c.path === MFA_PATH)?.body).toEqual({ code: "123456" });
    expect(await screen.findByRole("heading", { name: "Ada Lab" })).toBeInTheDocument();
  });
});

describe("members page", () => {
  const base = {
    [SESSION]: signedIn,
    "GET /api/labs/": { body: [] },
    "GET /api/labs/lab1/members/": {
      body: [
        {
          id: "m1",
          user: { id: "u1", email: "ada@uni.edu", display_name: "Ada" },
          role: "pi",
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    },
  };

  it("hides invite and management controls without manage_members", async () => {
    mockFetch({ ...base, "GET /api/labs/lab1/": { body: makeLab(["view_lab"], "viewer") } });
    renderRoute("/labs/lab1/members");
    expect(await screen.findByText("Ada")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Invite someone" })).not.toBeInTheDocument();
    expect(screen.queryByText("Pending invitations")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Remove/ })).not.toBeInTheDocument();
  });

  it("shows invites and validates the invite form with manage_members", async () => {
    const calls = mockFetch({
      ...base,
      "GET /api/labs/lab1/": { body: makeLab(["view_lab", "manage_members"]) },
      "GET /api/labs/lab1/invites/": {
        body: [
          {
            id: "i1",
            email: "new@uni.edu",
            role: "member",
            expires_at: "2026-12-01T00:00:00Z",
            created_at: "2026-11-01T00:00:00Z",
            invited_by: { id: "u1", email: "ada@uni.edu", display_name: "Ada" },
          },
        ],
      },
    });
    renderRoute("/labs/lab1/members");
    expect(await screen.findByRole("form", { name: "Invite someone" })).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Revoke invitation for new@uni.edu" }),
    ).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Email"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByText(/Enter a valid email address/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });
});

describe("accept invite", () => {
  const PREVIEW = "POST /api/invites/preview/";
  const preview = { body: { lab_name: "Ada Lab", role: "member", email: "grace@uni.edu" } };

  it("sends signed-out people to sign in or sign up and back", async () => {
    const calls = mockFetch({ [SESSION]: signedOut, [PREVIEW]: preview });
    document.cookie = "csrftoken=t";
    renderRoute("/invite/tok-1");
    expect(await screen.findByRole("heading", { name: "Join Ada Lab" })).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/invites/preview/")?.body).toEqual({ token: "tok-1" });
    expect(screen.getByRole("link", { name: "Sign in to accept" })).toHaveAttribute(
      "href",
      "/login?next=%2Finvite%2Ftok-1",
    );
    expect(screen.getByRole("link", { name: "Create an account" })).toHaveAttribute(
      "href",
      "/signup?next=%2Finvite%2Ftok-1",
    );
  });

  it("accepts when signed in and opens the lab", async () => {
    const lab = makeLab(["view_lab"], "member");
    const grace = {
      ...signedIn,
      body: { ...signedIn.body, data: { user: { id: 2, email: "grace@uni.edu" } } },
    };
    const calls = mockFetch({
      [SESSION]: grace,
      [PREVIEW]: preview,
      "POST /api/invites/accept/": { body: lab },
      "GET /api/labs/": { body: [lab] },
      "GET /api/labs/lab1/": { body: lab },
    });
    document.cookie = "csrftoken=t";
    renderRoute("/invite/tok-1");
    await userEvent.click(await screen.findByRole("button", { name: "Join Ada Lab" }));
    expect(await screen.findByRole("heading", { name: "Ada Lab" })).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/invites/accept/")?.body).toEqual({ token: "tok-1" });
  });

  it("explains a bad link", async () => {
    mockFetch({ [SESSION]: signedOut, [PREVIEW]: { status: 404, body: {} } });
    renderRoute("/invite/bad");
    expect(await screen.findByRole("heading", { name: /can't be used/ })).toBeInTheDocument();
  });
});
