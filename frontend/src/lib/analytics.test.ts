import { afterEach, describe, expect, it, vi } from "vitest";
import { beforeSend, identifyUser, pattern, scrubUrl, trackAction } from "@/lib/analytics";

const ID = "0d01f826-2e1a-469b-ac4c-1bafeb44b150";

describe("analytics scrubbing (D380)", () => {
  afterEach(() => {
    delete window.umami;
    identifyUser({ id: "u", email: "reset@uni.edu" }); // clears the excluded flag between tests
  });

  it("replaces ids, codes and tokens in paths", () => {
    expect(pattern(`/labs/${ID}/projects/${ID}/files`)).toBe("/labs/:id/projects/:id/files");
    expect(pattern("/invite/abc123")).toBe("/invite/:token");
    expect(pattern("/account/verify-email/MQ:1tA2b3:xyz")).toBe("/account/verify-email/:key");
    expect(pattern("/account/password/reset/key/1-abc")).toBe("/account/password/reset/key/:key");
    expect(pattern("/api/papers/12345/")).toBe("/api/papers/:n/");
    expect(pattern("/ZOOM_verify_9592a2e9e01a4e6ca36f69de6ebf7771.html")).toBe("/:token");
    expect(pattern("/settings?x=1#integrations")).toBe("/settings");
  });

  it("keeps only utm_* and a plain #tab, and never another site's path", () => {
    const o = window.location.origin;
    expect(
      scrubUrl(`${o}/labs/${ID}/chat?q=secret&utm_campaign=uofa-profs&next=%2Fx#integrations`),
    ).toBe(`${o}/labs/:id/chat?utm_campaign=uofa-profs#integrations`);
    expect(scrubUrl(`${o}/login#a b c`)).toBe(`${o}/login`);
    expect(scrubUrl("https://www.google.com/search?q=labbenchos")).toBe("https://www.google.com");
  });

  it("strips titles and scrubs urls and referrers before sending", () => {
    const o = window.location.origin;
    const out = beforeSend("event", {
      website: "w",
      title: "Pilot Attention Study (FAKE) - labbenchos",
      url: `${o}/labs/${ID}/documents/${ID}?q=participant+P-014`,
      referrer: `/invite/tok-123`,
      name: "click Save",
    });
    expect(out).toEqual({
      website: "w",
      title: "",
      url: `${o}/labs/:id/documents/:id`,
      referrer: "/invite/:token",
      name: "click Save",
    });
  });

  it("records actions by kind only, and marks failures", () => {
    const track = vi.fn();
    window.umami = { track, identify: vi.fn() };
    trackAction("GET", "/api/labs/", 200);
    trackAction("POST", `/api/labs/${ID}/projects/`, 201);
    trackAction("PATCH", `/api/labs/${ID}/tasks/${ID}/`, 400);
    trackAction("POST", "/_allauth/browser/v1/auth/login", 200);
    expect(track.mock.calls).toEqual([
      ["POST labs/:id/projects", { status: 201 }],
      ["FAIL PATCH labs/:id/tasks/:id", { status: 400 }],
      ["POST auth/login", { status: 200 }],
    ]);
  });

  it("leaves test accounts out and never sends a name or email", () => {
    const track = vi.fn();
    const identify = vi.fn();
    window.umami = { track, identify };
    identifyUser({ id: "u1", email: "pi@example.test" });
    trackAction("POST", "/api/labs/", 201);
    expect(track).not.toHaveBeenCalled();
    expect(identify).not.toHaveBeenCalled();
    identifyUser({ id: "u2", email: "ada@uni.edu" });
    trackAction("POST", "/api/labs/", 201);
    expect(identify).toHaveBeenCalledWith("u2");
    expect(track).toHaveBeenCalledTimes(1);
  });
});
