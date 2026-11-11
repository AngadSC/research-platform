import { describe, expect, it } from "vitest";
import {
  applyMention,
  cleanUrl,
  codeBlock,
  insertLink,
  mentionAt,
  mentionToken,
  prefixLines,
  wrap,
} from "@/lib/composerFormat";
import { EMOJI_GROUPS, searchEmoji } from "@/lib/emoji";

describe("wrap", () => {
  it("wraps the selection and keeps it selected", () => {
    const e = wrap("a big cat", 2, 5, "**");
    expect(e).toEqual({ value: "a **big** cat", start: 4, end: 7 });
  });
  it("with nothing selected, inserts a selected placeholder", () => {
    const e = wrap("hi ", 3, 3, "_", "_", "italic");
    expect(e.value).toBe("hi _italic_");
    expect(e.value.slice(e.start, e.end)).toBe("italic");
  });
  it("a second press takes the marks off again", () => {
    const e = wrap("a **big** cat", 4, 7, "**");
    expect(e).toEqual({ value: "a big cat", start: 2, end: 5 });
  });
});

describe("prefixLines", () => {
  it("numbers every touched line and not the others", () => {
    const e = prefixLines("x\none\ntwo\ny", 3, 9, "number");
    expect(e.value).toBe("x\n1. one\n2. two\ny");
  });
  it("adds and removes bullets and quotes", () => {
    const on = prefixLines("one\ntwo", 0, 7, "bullet");
    expect(on.value).toBe("- one\n- two");
    expect(prefixLines(on.value, on.start, on.end, "bullet").value).toBe("one\ntwo");
    expect(prefixLines("hi", 0, 0, "quote").value).toBe("> hi");
  });
  it("switches one kind of list to another", () => {
    expect(prefixLines("- a\n- b", 0, 7, "number").value).toBe("1. a\n2. b");
  });
});

describe("codeBlock and links", () => {
  it("fences the selection on its own lines", () => {
    const e = codeBlock("run x now", 4, 5);
    expect(e.value).toBe("run \n```\nx\n```\n now");
    expect(e.value.slice(e.start, e.end)).toBe("x");
  });
  it("makes a link from the selection, or from the address", () => {
    expect(insertLink("see docs", 4, 8, "https://e.org").value).toBe("see [docs](https://e.org)");
    expect(insertLink("", 0, 0, "https://e.org").value).toBe("[https://e.org](https://e.org)");
  });
  it("accepts web and email addresses only", () => {
    expect(cleanUrl("https://example.org/a")).toBe("https://example.org/a");
    expect(cleanUrl("example.org/a")).toBe("https://example.org/a");
    expect(cleanUrl("ada@example.test")).toBe("mailto:ada@example.test");
    for (const bad of ["", "javascript:alert(1)", "data:text/html,x", "two words.org", "a)b.org"])
      expect(cleanUrl(bad)).toBeNull();
  });
});

describe("mentions", () => {
  it("finds an @name being typed, only at a word start", () => {
    expect(mentionAt("hi @ad", 6)).toEqual({ start: 3, query: "ad" });
    expect(mentionAt("@", 1)).toEqual({ start: 0, query: "" });
    expect(mentionAt("mail me@example.test", 20)).toBeNull();
    expect(mentionAt("hi @ada there", 13)).toBeNull();
  });
  it("swaps the typed text for a stored token and a space", () => {
    const at = mentionAt("hi @ad", 6)!;
    const e = applyMention("hi @ad", at, "Ada Lovelace", "u-1");
    expect(e.value).toBe("hi @[Ada Lovelace](user:u-1) ");
    expect(e.start).toBe(e.value.length);
  });
  it("keeps brackets in a name from breaking the token", () => {
    expect(mentionToken("A [x](y)", "u")).toBe("@[A xy](user:u)");
  });
});

describe("emoji", () => {
  it("has a few groups and about 150 emoji", () => {
    expect(EMOJI_GROUPS.length).toBeGreaterThanOrEqual(4);
    const n = EMOJI_GROUPS.reduce((sum, g) => sum + g.items.length, 0);
    expect(n).toBeGreaterThanOrEqual(150);
  });
  it("searches by every word of the name", () => {
    expect(searchEmoji("microscope").map(([e]) => e)).toEqual(["🔬"]);
    expect(searchEmoji("thumbs up").map(([e]) => e)).toContain("👍");
    expect(searchEmoji("zzzzzz")).toEqual([]);
  });
});
