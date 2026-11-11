type Inline = { text?: string; content?: Inline[]; type?: string; props?: { name?: string } };
type Block = { content?: unknown; children?: unknown };

const inline = (items: Inline[]): string =>
  items
    .map((c) =>
      c.type === "mention" ? `@${c.props?.name ?? ""}` : (c.text ?? inline(c.content ?? [])),
    )
    .join("");

/** Plain text of a BlockNote block tree: one line per block, children indented. */
export function blocksToText(blocks: unknown, depth = 0): string {
  if (!Array.isArray(blocks)) return "";
  return (blocks as Block[])
    .flatMap((b) => [
      "  ".repeat(depth) + (Array.isArray(b.content) ? inline(b.content as Inline[]) : ""),
      blocksToText(b.children, depth + 1),
    ])
    .filter(Boolean)
    .join("\n");
}
