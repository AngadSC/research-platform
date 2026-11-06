import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const me = { id: "u1", email: "ada@uni.edu", display_name: "Ada", preferences: {} };
const KEY = "sk-ant-api03-SECRETKEYabcdefghijklmnop1234";
const status = (provider: string, saved: boolean, extra = {}) => ({
  provider,
  label: provider === "anthropic" ? "Anthropic (Claude)" : "OpenAI",
  saved,
  last4: saved ? "1234" : "",
  updated_at: saved ? "2026-11-05T10:00:00Z" : null,
  refusal_fallback: true,
  ...extra,
});

const base = (extra = {}, perms = ["view_lab"]) => ({
  [SESSION]: signedIn,
  "GET /api/me/": { body: me },
  "GET /api/labs/": { body: [makeLab(perms, perms.includes("manage_lab") ? "pi" : "member")] },
  "GET /api/ai/grants/": { body: [] },
  "GET /api/labs/lab1/ai-grants/": { body: [] },
  "GET /api/labs/lab1/ai-policy/": { body: { ai_policy: "full" } },
  ...extra,
});

afterEach(() => vi.unstubAllGlobals());

describe("settings: assistant API keys", () => {
  it("saves a key, shows only its last four characters, and clears the field", async () => {
    let saved = false;
    const calls = mockFetch(
      base({
        "GET /api/ai/keys/": () => ({
          body: [status("anthropic", saved), status("openai", false)],
        }),
        "PUT /api/ai/keys/anthropic/": () => {
          saved = true;
          return { body: status("anthropic", true) };
        },
      }),
    );
    renderRoute("/settings");
    const row = await screen.findByRole("group", { name: "Anthropic (Claude) key" });
    expect(within(row).getByText("Not saved")).toBeInTheDocument();
    const input = within(row).getByLabelText("Anthropic (Claude) API key");
    expect(input).toHaveAttribute("type", "password");
    expect(within(row).getByRole("button", { name: "Check and save" })).toBeDisabled();
    await userEvent.type(input, KEY);
    await userEvent.click(within(row).getByRole("button", { name: "Check and save" }));

    expect(await within(row).findByText("Saved: ending 1234")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ api_key: KEY });
    expect(input).toHaveValue("");
    expect(document.body.textContent).not.toContain(KEY);
    expect(
      within(row).getByRole("button", { name: "Remove Anthropic (Claude) key" }),
    ).toBeInTheDocument();
  });

  it("shows the provider's rejection next to the field and does not claim success", async () => {
    mockFetch(
      base({
        "GET /api/ai/keys/": { body: [status("anthropic", false), status("openai", false)] },
        "PUT /api/ai/keys/openai/": {
          status: 400,
          body: { api_key: ["OpenAI rejected your API key. Check it in Settings > AI."] },
        },
      }),
    );
    renderRoute("/settings");
    const row = await screen.findByRole("group", { name: "OpenAI key" });
    await userEvent.type(
      within(row).getByLabelText("OpenAI API key"),
      "sk-proj-wrongwrongwrongwrong",
    );
    await userEvent.click(within(row).getByRole("button", { name: "Check and save" }));
    expect(await within(row).findByRole("alert")).toHaveTextContent(/rejected your API key/);
    expect(within(row).getByText("Not saved")).toBeInTheDocument();
  });

  it("removes a key", async () => {
    const calls = mockFetch(
      base({
        "GET /api/ai/keys/": { body: [status("anthropic", true), status("openai", false)] },
        "DELETE /api/ai/keys/anthropic/": { status: 204 },
      }),
    );
    renderRoute("/settings");
    await userEvent.click(
      await screen.findByRole("button", { name: "Remove Anthropic (Claude) key" }),
    );
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("lets the person turn the refusal fallback off", async () => {
    const calls = mockFetch(
      base({
        "GET /api/ai/keys/": { body: [status("anthropic", true), status("openai", false)] },
        "PATCH /api/ai/keys/anthropic/": {
          body: status("anthropic", true, { refusal_fallback: false }),
        },
      }),
    );
    renderRoute("/settings");
    const box = await screen.findByRole("checkbox", {
      name: /retry it automatically on another model/,
    });
    expect(box).toBeChecked();
    await userEvent.click(box);
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ refusal_fallback: false }),
    );
  });

  it("says the provider sees record content and warns about participant identifiers", async () => {
    mockFetch(
      base({
        "GET /api/ai/keys/": { body: [status("anthropic", false), status("openai", false)] },
      }),
    );
    renderRoute("/settings");
    const section = await screen.findByRole("region", { name: "Assistant API keys" });
    expect(within(section).getByText(/Do not paste participant identifiers/)).toBeInTheDocument();
  });
});

describe("settings: the lab's AI policy", () => {
  it("is shown to a PI with the three choices and a notice, and saves a change", async () => {
    const calls = mockFetch(
      base(
        {
          "GET /api/ai/keys/": { body: [] },
          "PATCH /api/labs/lab1/ai-policy/": { body: { ai_policy: "off" } },
        },
        ["view_lab", "manage_lab", "manage_lab_integrations"],
      ),
    );
    renderRoute("/settings");
    const section = await screen.findByRole("region", { name: "AI assistants in Ada Lab" });
    expect(within(section).getByText(/Allowed by default/)).toBeInTheDocument();
    expect(within(section).getByText(/may need to choose Off/)).toBeInTheDocument();
    const full = await within(section).findByRole("radio", { name: /MCP and in-app assistant/ });
    await waitFor(() => expect(full).toBeChecked());
    expect(within(section).getByRole("radio", { name: /MCP only/ })).not.toBeChecked();
    await userEvent.click(within(section).getByRole("radio", { name: /^Off/ }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ ai_policy: "off" }),
    );
  });

  it("is not shown to a member", async () => {
    mockFetch(base({ "GET /api/ai/keys/": { body: [] } }));
    renderRoute("/settings");
    await screen.findByRole("region", { name: "Assistant API keys" });
    expect(screen.queryByRole("region", { name: /AI assistants in/ })).not.toBeInTheDocument();
  });
});
