import { describe, expect, it } from "vitest";
import {
  applyMention,
  cleanUrl,
  codeBlock,
  insertLink,
  mentionAt,
  mentionToken,
  nameIndex,
  prefixLines,
  toDisplay,
  toStored,
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
  it("swaps the typed text for the person's name and a space", () => {
    const at = mentionAt("hi @ad", 6)!;
    const e = applyMention("hi @ad", at, "Ada Lovelace");
    expect(e.value).toBe("hi @Ada Lovelace ");
    expect(e.start).toBe(e.value.length);
  });
  it("keeps brackets in a name from breaking the token", () => {
    expect(mentionToken("A [x](y)", "u")).toBe("@[A x(y)](user:u)");
    expect(mentionToken("Lee Lead (FAKE)", "u")).toBe("@[Lee Lead (FAKE)](user:u)");
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

const ID_A = "11111111-1111-1111-1111-111111111111";
const ID_B = "22222222-2222-2222-2222-222222222222";
const ID_C = "33333333-3333-3333-3333-333333333333";
const ada = { id: ID_A, name: "Ada Lovelace" };
const grace = { id: ID_B, name: "Grace Hopper" };

describe("mentions shown as names (D295)", () => {
  it("shows a stored mention as just the name", () => {
    expect(toDisplay(`hi @[Ada Lovelace](user:${ID_A}), and @[Grace Hopper](user:${ID_B})!`)).toBe(
      "hi @Ada Lovelace, and @Grace Hopper!",
    );
    expect(toDisplay("no mentions @here or [a](https://x.org)")).toBe(
      "no mentions @here or [a](https://x.org)",
    );
  });

  it("turns a written-out @Name back into the stored mention", () => {
    const index = nameIndex([ada, grace], "");
    expect(toStored("hi @Ada Lovelace, and @Grace Hopper!", index)).toBe(
      `hi ${mentionToken("Ada Lovelace", ID_A)}, and ${mentionToken("Grace Hopper", ID_B)}!`,
    );
  });

  it("is lossless: what is stored shows and converts back unchanged", () => {
    const stored = `see @[Ada Lovelace](user:${ID_A}) now\n- @[Grace Hopper](user:${ID_B})`;
    expect(toStored(toDisplay(stored), nameIndex([], stored))).toBe(stored);
  });

  it("keeps a mention of someone no longer in the list, from the stored text", () => {
    const stored = `thanks @[Old Colleague](user:${ID_C})`;
    expect(toStored(toDisplay(stored), nameIndex([ada], stored))).toBe(stored);
  });

  it("leaves a half-deleted name, an email address and a longer word as typed", () => {
    const index = nameIndex([ada, { id: ID_C, name: "Al" }], "");
    expect(toStored("hi @Ada Lovelac", index)).toBe("hi @Ada Lovelac");
    expect(toStored("mail me@Ada Lovelace", index)).toBe("mail me@Ada Lovelace");
    expect(toStored("@Alex is not Al", index)).toBe("@Alex is not Al");
    expect(toStored("@ada lovelace", index)).toBe("@ada lovelace"); // not the written name
  });

  it("picks the longest name, and allows punctuation after it", () => {
    const index = nameIndex([{ id: ID_C, name: "Ada" }, ada], "");
    expect(toStored("@Ada Lovelace.", index)).toBe(`${mentionToken("Ada Lovelace", ID_A)}.`);
    expect(toStored("@Ada, hello", index)).toBe(`${mentionToken("Ada", ID_C)}, hello`);
  });

  it("does not guess when two people share a name", () => {
    const index = nameIndex(
      [
        { id: ID_A, name: "Sam Lee" },
        { id: ID_B, name: "Sam Lee" },
      ],
      "",
    );
    expect(toStored("@Sam Lee", index)).toBe("@Sam Lee"); // plain text, nobody wrongly told
  });

  it("works with names that hold brackets, and with text that has no @", () => {
    const index = nameIndex([{ id: ID_A, name: "Ada (PI)" }], "");
    expect(toStored("@Ada (PI) hi", index)).toBe(`${mentionToken("Ada (PI)", ID_A)} hi`);
    expect(toStored("plain text", index)).toBe("plain text");
    expect(toStored("anything @x", new Map())).toBe("anything @x");
  });

  it("does not touch a token typed or pasted in full", () => {
    const pasted = `@[Ada Lovelace](user:${ID_A}) hi`;
    expect(toStored(pasted, nameIndex([ada], ""))).toBe(pasted);
  });
});

describe("mentions and code (D295)", () => {
  const index = nameIndex([ada], "");
  const token = mentionToken("Ada Lovelace", ID_A);
  it("does not turn a name inside inline code or a code block into a mention", () => {
    expect(toStored("run `@Ada Lovelace` now", index)).toBe("run `@Ada Lovelace` now");
    expect(toStored("```\n@Ada Lovelace\n```", index)).toBe("```\n@Ada Lovelace\n```");
    expect(toStored("```\nstill typing @Ada Lovelace", index)).toBe(
      "```\nstill typing @Ada Lovelace",
    );
  });
  it("still converts a name next to code, in the normal text", () => {
    expect(toStored("@Ada Lovelace see `x`", index)).toBe(`${token} see \`x\``);
    expect(toStored("`x` then @Ada Lovelace", index)).toBe(`\`x\` then ${token}`);
  });
  it("does not count the end of a code span as the start of a word", () => {
    expect(toStored("`x`@Ada Lovelace", index)).toBe("`x`@Ada Lovelace");
  });
});
