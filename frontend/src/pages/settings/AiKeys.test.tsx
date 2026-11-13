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
  "GET /api/labs/lab1/assistant/config/": { body: config(null) },
  "GET /api/labs/lab1/ai-key/": { body: labKey(false) },
  ...extra,
});

type LabKeyAvailability = {
  provider: string;
  label: string;
  own_key_wins: boolean;
  limit_reached: boolean;
};
function config(lab_key: LabKeyAvailability | null) {
  return { ai_policy: "full", can_use: true, providers: [], privacy_notice: "", lab_key };
}
const available = (extra = {}) => ({
  provider: "anthropic",
  label: "Anthropic (Claude)",
  own_key_wins: false,
  limit_reached: false,
  ...extra,
});
function labKey(saved: boolean, extra = {}) {
  return {
    saved,
    provider: saved ? "anthropic" : null,
    label: saved ? "Anthropic (Claude)" : "",
    last4: saved ? "9876" : "",
    monthly_cap_usd: saved ? "50.00" : null,
    updated_at: saved ? "2026-11-05T10:00:00Z" : null,
    month: "2026-11-01",
    spent_usd: "0.00",
    usage: [],
    ...extra,
  };
}

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
    renderRoute("/settings#ai");
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
    renderRoute("/settings#ai");
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
    renderRoute("/settings#ai");
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
    renderRoute("/settings#ai");
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
    renderRoute("/settings#ai");
    const section = await screen.findByRole("region", { name: "Assistant API keys" });
    expect(within(section).getByText(/Do not paste participant identifiers/)).toBeInTheDocument();
  });
});

describe("admin: the lab's AI policy", () => {
  it("is on Admin's AI tab with the three choices and a notice, and saves a change", async () => {
    const calls = mockFetch(
      base(
        {
          "GET /api/ai/keys/": { body: [] },
          "GET /api/labs/lab1/": { body: makeLab(["view_lab", "manage_lab"]) },
          "PATCH /api/labs/lab1/ai-policy/": { body: { ai_policy: "off" } },
        },
        ["view_lab", "manage_lab", "manage_lab_integrations"],
      ),
    );
    renderRoute("/labs/lab1/admin#ai");
    const section = await screen.findByRole("region", { name: "AI assistants in Ada Lab" });
    expect(within(section).getByText(/Allowed by default/)).toBeInTheDocument();
    expect(within(section).getByText(/may need to choose Off/)).toBeInTheDocument();
    const full = await within(section).findByRole("radio", {
      name: /Connected apps \(like Claude\) and the in-app assistant/,
    });
    await waitFor(() => expect(full).toBeChecked());
    expect(within(section).getByRole("radio", { name: /Connected apps only/ })).not.toBeChecked();
    await userEvent.click(within(section).getByRole("radio", { name: /^Off/ }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ ai_policy: "off" }),
    );
  });

  it("has left Settings", async () => {
    mockFetch(
      base({ "GET /api/ai/keys/": { body: [] } }, [
        "view_lab",
        "manage_lab",
        "manage_lab_integrations",
      ]),
    );
    renderRoute("/settings#ai");
    await screen.findByRole("region", { name: "Assistant API keys" });
    expect(screen.queryByRole("region", { name: /AI assistants in/ })).not.toBeInTheDocument();
  });
});

describe("the lab's AI key", () => {
  const admin = ["view_lab", "manage_lab", "manage_lab_integrations"];
  const LAB_KEY = "sk-ant-api03-LABKEYabcdefghijklmnop9876";

  it("lets a PI set the key with a monthly limit, never keeping the key in the page", async () => {
    let saved = false;
    const calls = mockFetch(
      base(
        {
          "GET /api/ai/keys/": { body: [] },
          "GET /api/labs/lab1/": { body: makeLab(admin) },
          "GET /api/labs/lab1/ai-key/": () => ({ body: labKey(saved) }),
          "PUT /api/labs/lab1/ai-key/": () => {
            saved = true;
            return { body: labKey(true) };
          },
        },
        admin,
      ),
    );
    renderRoute("/labs/lab1/admin#ai");
    const section = await screen.findByRole("region", { name: "Lab AI key" });
    expect(await within(section).findByText(/No lab key yet/)).toBeInTheDocument();
    const save = within(section).getByRole("button", { name: "Check and save" });
    await userEvent.type(within(section).getByLabelText("API key"), LAB_KEY);
    expect(save).toBeDisabled(); // a limit is required
    await userEvent.type(within(section).getByLabelText("Monthly limit (USD)"), "50");
    await userEvent.click(save);

    expect(await within(section).findByText("Saved: ending 9876")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      provider: "anthropic",
      api_key: LAB_KEY,
      monthly_cap_usd: "50",
    });
    expect(within(section).getByLabelText("API key")).toHaveValue("");
    expect(document.body.textContent).not.toContain(LAB_KEY);
  });

  it("shows this month's use per person and the total, and changes the limit", async () => {
    const calls = mockFetch(
      base(
        {
          "GET /api/ai/keys/": { body: [] },
          "GET /api/labs/lab1/": { body: makeLab(admin) },
          "GET /api/labs/lab1/ai-key/": {
            body: labKey(true, {
              spent_usd: "1.75",
              usage: [
                { user: "u2", name: "Grace", cost_usd: "1.50", input_tokens: 9, output_tokens: 1 },
                { user: "u1", name: "Ada", cost_usd: "0.25", input_tokens: 3, output_tokens: 1 },
              ],
            }),
          },
          "PATCH /api/labs/lab1/ai-key/": { body: labKey(true, { monthly_cap_usd: "80.00" }) },
          "DELETE /api/labs/lab1/ai-key/": { status: 204 },
        },
        admin,
      ),
    );
    renderRoute("/labs/lab1/admin#ai");
    const section = await screen.findByRole("region", { name: "Lab AI key" });
    expect(await within(section).findByText("This month: $1.75 of $50.00")).toBeInTheDocument();
    const table = within(section).getByRole("table", { name: "Use of the lab key this month" });
    expect(within(table).getByText("Grace")).toBeInTheDocument();
    expect(within(table).getByText("$1.50")).toBeInTheDocument();
    await userEvent.type(within(section).getByLabelText("Change the monthly limit (USD)"), "80");
    await userEvent.click(within(section).getByRole("button", { name: "Save limit" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ monthly_cap_usd: "80" }),
    );
    await userEvent.click(within(section).getByRole("button", { name: "Remove lab key" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it.each([
    [null, /Ada Lab has no lab AI key/],
    [available(), /Ada Lab has a lab key for Anthropic \(Claude\)\. You can use the assistant/],
    [available({ own_key_wins: true }), /your own Anthropic \(Claude\) key is used first/],
    [available({ limit_reached: true }), /reached this month's limit/],
  ])("tells a member in Settings whether the lab key is there for them", async (k, text) => {
    mockFetch(
      base({
        "GET /api/ai/keys/": { body: [] },
        "GET /api/labs/lab1/assistant/config/": { body: config(k) },
      }),
    );
    renderRoute("/settings#ai");
    expect(await screen.findByText(text)).toBeInTheDocument();
  });
});
