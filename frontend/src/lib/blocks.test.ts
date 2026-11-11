import { describe, expect, it } from "vitest";
import { blocksToText } from "@/lib/blocks";

describe("blocksToText", () => {
  it("writes a mention as @Name", () => {
    const blocks = [
      {
        type: "paragraph",
        content: [
          { type: "text", text: "ask ", styles: {} },
          { type: "mention", props: { userId: "u1", name: "Ada" } },
        ],
        children: [],
      },
    ];
    expect(blocksToText(blocks)).toBe("ask @Ada");
  });
});
