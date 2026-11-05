import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { mockFetch, renderRoute, SESSION, signedOut } from "@/test/utils";

const B = "/_allauth/browser/v1";
const METHODS = "POST /api/auth/login-methods/";
const ualberta = {
  id: "saml:ualberta",
  name: "University of Alberta",
  flows: ["provider_redirect"],
};
const config = { body: { status: 200, data: { socialaccount: { providers: [ualberta] } } } };

beforeEach(() => {
  document.cookie = "csrftoken=tok";
  sessionStorage.clear();
});

async function enterEmail(email: string) {
  await userEvent.type(await screen.findByLabelText("Email"), email);
  await userEvent.click(screen.getByRole("button", { name: "Continue" }));
}

describe("email-first sign-in (D156)", () => {
  it("sends an institution address to its SSO with a native form POST", async () => {
    const calls = mockFetch({
      [SESSION]: signedOut,
      [`GET ${B}/config`]: config,
      [METHODS]: {
        body: { methods: ["saml:ualberta", "password"], institution: "University of Alberta" },
      },
    });
    renderRoute("/login?next=%2Flabs");
    await enterEmail("ada@ualberta.ca");
    const btn = await screen.findByRole("button", { name: "Continue with University of Alberta" });
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ email: "ada@ualberta.ca" });
    const form = btn.closest("form")!;
    expect(form.getAttribute("action")).toBe(`${B}/auth/provider/redirect`);
    expect(Object.fromEntries(new FormData(form).entries())).toEqual({
      provider: "saml:ualberta",
      process: "login",
      callback_url: "/account/provider/callback",
      csrfmiddlewaretoken: "tok",
    });
    expect(screen.queryByLabelText("Password")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Use a password instead" }));
    expect(await screen.findByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveValue("ada@ualberta.ca");
  });

  it("offers no password when the institution requires SSO", async () => {
    mockFetch({
      [SESSION]: signedOut,
      [`GET ${B}/config`]: config,
      [METHODS]: { body: { methods: ["saml:ualberta"], institution: "University of Alberta" } },
    });
    renderRoute("/login");
    await enterEmail("ada@ualberta.ca");
    await screen.findByRole("button", { name: "Continue with University of Alberta" });
    expect(screen.queryByRole("button", { name: "Use a password instead" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Use a different email" }));
    expect(await screen.findByRole("button", { name: "Continue" })).toBeInTheDocument();
  });

  it("shows the password form for other addresses, and when the lookup fails", async () => {
    mockFetch({
      [SESSION]: signedOut,
      [`GET ${B}/config`]: config,
      [METHODS]: { status: 500, body: null },
    });
    renderRoute("/login");
    await enterEmail("ada@example.com");
    expect(await screen.findByLabelText("Password")).toBeInTheDocument();
    expect(screen.queryByText(/Continue with University/)).toBeNull();
  });
});
