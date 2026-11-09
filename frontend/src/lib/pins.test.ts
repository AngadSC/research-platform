import { describe, expect, it } from "vitest";
import { addRecent, isLocalUrl, MAX_PINS, MAX_RECENTS, togglePin, type Recent } from "./pins";

const recent = (n: number, label = `Page ${n}`): Recent => ({
  url: `/p/${n}`,
  label,
  kind: "project",
  at: "2026-11-08T12:00:00.000Z",
});

describe("isLocalUrl", () => {
  it.each(["/", "/labs/1/projects/2", "/a?b=c#d"])("accepts %s", (url) => {
    expect(isLocalUrl(url)).toBe(true);
  });
  it.each(["//evil.example", "/\\evil.example", "/\t/evil.example", "https://x.y", "x", ""])(
    "refuses %j",
    (url) => expect(isLocalUrl(url)).toBe(false),
  );
});

describe("togglePin", () => {
  const pin = { url: "/a", label: "A" };
  it("adds, then removes", () => {
    expect(togglePin([], pin)).toEqual([pin]);
    expect(togglePin([pin], pin)).toEqual([]);
  });
  it("refuses another pin at the cap, but can still unpin", () => {
    const full = Array.from({ length: MAX_PINS }, (_, n) => ({ url: `/p/${n}`, label: "x" }));
    expect(togglePin(full, pin)).toBeNull();
    expect(togglePin(full, { url: "/p/0", label: "x" })).toHaveLength(MAX_PINS - 1);
  });
  it("refuses an address off this site", () => {
    expect(togglePin([], { url: "//evil.example", label: "x" })).toBeNull();
  });
});

describe("addRecent", () => {
  it("puts the newest first, without duplicates", () => {
    const next = addRecent([recent(1), recent(2)], recent(2));
    expect(next?.map((r) => r.url)).toEqual(["/p/2", "/p/1"]);
  });
  it("drops the oldest past the cap", () => {
    const full = Array.from({ length: MAX_RECENTS }, (_, n) => recent(n));
    const next = addRecent(full, recent(99));
    expect(next).toHaveLength(MAX_RECENTS);
    expect(next?.[0]?.url).toBe("/p/99");
    expect(next?.some((r) => r.url === `/p/${MAX_RECENTS - 1}`)).toBe(false);
  });
  it("has nothing to save when the top entry is unchanged", () => {
    expect(addRecent([recent(1)], recent(1))).toBeNull();
  });
  it("saves when the top entry was renamed", () => {
    expect(addRecent([recent(1)], recent(1, "New name"))?.[0]?.label).toBe("New name");
  });
});
