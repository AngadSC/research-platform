import { describe, expect, it } from "vitest";
import { toggleReaction } from "@/hooks/chat";

const r = (emoji: string, count: number, mine: boolean) => ({ emoji, count, mine, people: [] });

describe("toggleReaction", () => {
  it("adds yours, joins an existing one, and takes it back", () => {
    expect(toggleReaction([], "+1")).toEqual([r("+1", 1, true)]);
    expect(toggleReaction([r("+1", 2, false)], "+1")).toEqual([r("+1", 3, true)]);
    expect(toggleReaction([r("+1", 2, true)], "+1")).toEqual([r("+1", 1, false)]);
    expect(toggleReaction([r("+1", 1, true), r("ok", 1, false)], "+1")).toEqual([
      r("ok", 1, false),
    ]);
  });
});
