import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { mockFetch, renderRoute, SESSION, signedOut } from "@/test/utils";

const B = "/_allauth/browser/v1";
const CONFIG = `GET ${B}/config`;
const google = { id: "google", name: "Google", flows: ["provider_redirect"] };
const withGoogle = { body: { status: 200, data: { socialaccount: { providers: [google] } } } };
const noGoogle = { body: { status: 200, data: { socialaccount: { providers: [] } } } };
const userWith = (pw: boolean) => ({
  status: 200,
  body: {
    status: 200,
    data: { user: { id: 1, email: "ada@uni.edu", has_usable_password: pw } },
    meta: { is_authenticated: true },
  },
});

beforeEach(() => {
  document.cookie = "csrftoken=tok";
  sessionStorage.clear();
});

describe("Continue with Google", () => {
  it("is hidden when no Google provider is configured", async () => {
    mockFetch({ [SESSION]: signedOut, [CONFIG]: noGoogle });
    renderRoute("/login");
    await screen.findByRole("button", { name: "Continue" });
    await waitFor(() => expect(screen.queryByText("Continue with Google")).toBeNull());
  });

  it("posts a native form with provider, process, callback and CSRF token", async () => {
    mockFetch({ [SESSION]: signedOut, [CONFIG]: withGoogle });
    renderRoute("/signup");
    const btn = await screen.findByRole("button", { name: "Continue with Google" });
    const form = btn.closest("form")!;
    expect(form.method).toBe("post");
    expect(form.getAttribute("action")).toBe(`${B}/auth/provider/redirect`);
    const f = Object.fromEntries(new FormData(form).entries());
    expect(f).toEqual({
      provider: "google",
      process: "login",
      callback_url: "/account/provider/callback",
      csrfmiddlewaretoken: "tok",
    });
  });
});

describe("provider callback", () => {
  it("explains a failed sign-in", async () => {
    mockFetch({});
    renderRoute("/account/provider/callback?error=access_denied");
    expect(await screen.findByText("Sign-in did not finish")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to sign in" })).toBeInTheDocument();
  });

  it("sends a pending email verification to the check-email page", async () => {
    mockFetch({
      [SESSION]: {
        status: 401,
        body: {
          status: 401,
          data: { flows: [{ id: "verify_email", is_pending: true }] },
          meta: { is_authenticated: false },
        },
      },
      [CONFIG]: noGoogle,
    });
    renderRoute("/account/provider/callback");
    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
  });
});

describe("connected accounts", () => {
  const account = { uid: "1", display: "ada@gmail.com", provider: google };
  const emails = `GET ${B}/account/email`;

  function setup(pw: boolean, accounts: unknown[]) {
    return mockFetch({
      [SESSION]: userWith(pw),
      [CONFIG]: withGoogle,
      [`GET ${B}/account/providers`]: { body: { status: 200, data: accounts } },
      [`DELETE ${B}/account/providers`]: { body: { status: 200, data: [] } },
      [emails]: { body: { status: 200, data: [] } },
      [`GET ${B}/account/authenticators/totp`]: { status: 404, body: { meta: { secret: "S" } } },
    });
  }

  it("blocks disconnect without a password and explains why", async () => {
    setup(false, [account]);
    renderRoute("/account");
    expect(await screen.findByText("ada@gmail.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeDisabled();
    expect(screen.getByText(/Set a password first/)).toBeInTheDocument();
  });

  it("disconnects when a password exists", async () => {
    const calls = setup(true, [account]);
    renderRoute("/account");
    await userEvent.click(await screen.findByRole("button", { name: "Disconnect" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "DELETE")?.body).toEqual({
        provider: "google",
        account: "1",
      }),
    );
  });

  it("offers Connect with the connect process when not connected", async () => {
    setup(true, []);
    renderRoute("/account");
    const btn = await screen.findByRole("button", { name: "Connect Google" });
    expect(new FormData(btn.closest("form")!).get("process")).toBe("connect");
  });
});

describe("email addresses", () => {
  const list = [
    { email: "ada@uni.edu", primary: true, verified: true },
    { email: "ada@home.org", primary: false, verified: true },
    { email: "new@home.org", primary: false, verified: false },
  ];
  const E = `${B}/account/email`;

  function setup() {
    return mockFetch({
      [SESSION]: userWith(true),
      [CONFIG]: noGoogle,
      [`GET ${B}/account/providers`]: { body: { status: 200, data: [] } },
      [`GET ${E}`]: { body: { status: 200, data: list } },
      [`POST ${E}`]: { body: { status: 200, data: list } },
      [`PUT ${E}`]: { body: { status: 200 } },
      [`PATCH ${E}`]: { body: { status: 200, data: list } },
      [`DELETE ${E}`]: { body: { status: 200, data: list } },
      [`GET ${B}/account/authenticators/totp`]: { status: 404, body: { meta: { secret: "S" } } },
    });
  }

  it("lists badges and runs add, resend, make primary and remove", async () => {
    const calls = setup();
    renderRoute("/account");
    const home = (await screen.findByText("ada@home.org")).closest("li")!;
    const fresh = screen.getByText("new@home.org").closest("li")!;
    expect(
      within(screen.getByText("ada@uni.edu").closest("li")!).getByText("Primary"),
    ).toBeTruthy();
    expect(within(fresh).getByText("Not verified")).toBeTruthy();
    expect(screen.getByText(/invitations work with any verified address/i)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Add an email address"), "x@y.org");
    await userEvent.click(screen.getByRole("button", { name: "Add email" }));
    await userEvent.click(within(fresh).getByRole("button", { name: "Resend verification" }));
    await userEvent.click(within(home).getByRole("button", { name: "Make primary" }));
    await userEvent.click(within(home).getByRole("button", { name: "Remove" }));

    await waitFor(() =>
      expect(calls.filter((c) => c.path === E && c.method !== "GET")).toHaveLength(4),
    );
    const body = (m: string) => calls.find((c) => c.path === E && c.method === m)?.body;
    expect(body("POST")).toEqual({ email: "x@y.org" });
    expect(body("PUT")).toEqual({ email: "new@home.org" });
    expect(body("PATCH")).toEqual({ email: "ada@home.org", primary: true });
    expect(body("DELETE")).toEqual({ email: "ada@home.org" });
  });
});

describe("reauthentication (D74)", () => {
  const E = `${B}/account/email`;
  const flows = (ids: string[]) => ({
    status: 401,
    body: {
      status: 401,
      data: { flows: ids.map((id) => ({ id })) },
      meta: { is_authenticated: true },
    },
  });
  const base = {
    [SESSION]: userWith(true),
    [CONFIG]: noGoogle,
    [`GET ${B}/account/providers`]: { body: { status: 200, data: [] } },
    [`GET ${E}`]: { body: { status: 200, data: [] } },
    [`GET ${B}/account/authenticators/totp`]: { status: 404, body: { meta: { secret: "S" } } },
  };

  it("asks for the password after a 401, then retries the action", async () => {
    let tries = 0;
    const calls = mockFetch({
      ...base,
      [`POST ${E}`]: () =>
        ++tries === 1 ? flows(["reauthenticate"]) : { body: { status: 200, data: [] } },
      [`POST ${B}/auth/reauthenticate`]: { body: { status: 200 } },
    });
    renderRoute("/account");
    await userEvent.type(await screen.findByLabelText("Add an email address"), "x@y.org");
    await userEvent.click(screen.getByRole("button", { name: "Add email" }));
    await userEvent.type(await screen.findByLabelText("Password"), "hunter2hunter2");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() =>
      expect(calls.filter((c) => c.path === E && c.method === "POST")).toHaveLength(2),
    );
    expect(calls.find((c) => c.path === `${B}/auth/reauthenticate`)?.body).toEqual({
      password: "hunter2hunter2",
    });
  });

  it("also asks for the TOTP code when the account has two-step verification", async () => {
    let tries = 0;
    const calls = mockFetch({
      ...base,
      [`DELETE ${E}`]: () =>
        ++tries === 1
          ? flows(["reauthenticate", "mfa_reauthenticate"])
          : { body: { status: 200, data: [] } },
      [`GET ${E}`]: {
        body: {
          status: 200,
          data: [
            { email: "ada@uni.edu", primary: true, verified: true },
            { email: "b@home.org", primary: false, verified: true },
          ],
        },
      },
      [`POST ${B}/auth/reauthenticate`]: { body: { status: 200 } },
      [`POST ${B}/auth/2fa/reauthenticate`]: { body: { status: 200 } },
    });
    renderRoute("/account");
    const row = (await screen.findByText("b@home.org")).closest("li")!;
    await userEvent.click(within(row).getByRole("button", { name: "Remove" }));
    await userEvent.type(await screen.findByLabelText("Password"), "pw-pw-pw-pw");
    const dialog = within(screen.getByRole("dialog"));
    await userEvent.type(dialog.getByLabelText("6-digit code"), "123456");
    await userEvent.click(dialog.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "DELETE")).toHaveLength(2));
    expect(calls.find((c) => c.path === `${B}/auth/2fa/reauthenticate`)?.body).toEqual({
      code: "123456",
    });
  });

  it("asks only for the code when there is no usable password", async () => {
    let tries = 0;
    mockFetch({
      ...base,
      [SESSION]: userWith(false),
      [`POST ${E}`]: () =>
        ++tries === 1 ? flows(["mfa_reauthenticate"]) : { body: { status: 200, data: [] } },
      [`POST ${B}/auth/2fa/reauthenticate`]: { body: { status: 200 } },
    });
    renderRoute("/account");
    await userEvent.type(await screen.findByLabelText("Add an email address"), "x@y.org");
    await userEvent.click(screen.getByRole("button", { name: "Add email" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByLabelText("6-digit code")).toBeInTheDocument();
    expect(dialog.queryByLabelText("Password")).toBeNull();
  });

  it("asks before connecting Google, and does not retry when cancelled", async () => {
    const calls = mockFetch({ ...base, [CONFIG]: withGoogle });
    renderRoute("/account");
    await userEvent.click(await screen.findByRole("button", { name: "Connect Google" }));
    await screen.findByLabelText("Password");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByLabelText("Password")).toBeNull());
    expect(calls.some((c) => c.path.includes("reauthenticate"))).toBe(false);
  });
});
