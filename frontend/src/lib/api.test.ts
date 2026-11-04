import { afterEach, describe, expect, it } from "vitest";
import { api, ApiError } from "@/lib/api";
import { mockFetch, SESSION, SESSION_PATH } from "@/test/utils";

afterEach(() => {
  document.cookie = "csrftoken=; max-age=0";
});

describe("api", () => {
  it("fetches the session first to get a CSRF cookie, then sends it on POST", async () => {
    const calls = mockFetch({
      [SESSION]: () => {
        document.cookie = "csrftoken=tok123";
        return { status: 401, body: {} };
      },
      "POST /api/labs/": { status: 201, body: { id: "x" } },
    });
    await api("/api/labs/", { method: "POST", body: { name: "A" } });
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      `GET ${SESSION_PATH}`,
      "POST /api/labs/",
    ]);
    expect(calls[1]?.headers["X-CSRFToken"]).toBe("tok123");
    expect(calls[1]?.body).toEqual({ name: "A" });
  });

  it("does not send CSRF on GET", async () => {
    const calls = mockFetch({ "GET /api/me/": { body: {} } });
    await api("/api/me/");
    expect(calls).toHaveLength(1);
    expect(calls[0]?.headers["X-CSRFToken"]).toBeUndefined();
  });

  it.each([
    [401, /sign in/i],
    [403, /permission/i],
    [404, /find that/i],
    [409, /conflicts/i],
    [500, /our side/i],
  ])("maps %i to a readable message", async (status, text) => {
    mockFetch({ "GET /api/x/": { status, body: {} } });
    const err = await api("/api/x/").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(status);
    expect((err as ApiError).message).toMatch(text);
  });

  it("keeps field errors from DRF and allauth bodies", async () => {
    mockFetch({
      "GET /a/": { status: 400, body: { email: ["Enter a valid email."] } },
      "GET /b/": { status: 400, body: { errors: [{ message: "Too short", param: "password" }] } },
      "GET /c/": { status: 403, body: { detail: "Wrong account." } },
    });
    const a = (await api("/a/").catch((e: unknown) => e)) as ApiError;
    expect(a.fieldErrors).toEqual({ email: "Enter a valid email." });
    const b = (await api("/b/").catch((e: unknown) => e)) as ApiError;
    expect(b.fieldErrors).toEqual({ password: "Too short" });
    const c = (await api("/c/").catch((e: unknown) => e)) as ApiError;
    expect(c.message).toBe("Wrong account.");
  });
});
