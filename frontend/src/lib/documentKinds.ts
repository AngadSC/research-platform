import { FileText, Presentation, Sheet, type LucideIcon } from "lucide-react";
import { emptyBlock } from "@/lib/sheet";

export type DocKind = "doc" | "sheet" | "slides";

/** What a new document can be, with the title and starting content each one begins with. */
export const DOC_KINDS: {
  kind: DocKind;
  label: string;
  title: string;
  icon: LucideIcon;
  content: () => unknown[];
}[] = [
  { kind: "doc", label: "Document", title: "Untitled document", icon: FileText, content: () => [] },
  {
    kind: "sheet",
    label: "Spreadsheet",
    title: "Untitled spreadsheet",
    icon: Sheet,
    content: () => [emptyBlock()],
  },
  {
    kind: "slides",
    label: "Presentation",
    title: "Untitled presentation",
    icon: Presentation,
    content: () => [
      {
        type: "slide",
        props: { layout: "title" },
        title: { text: "" },
        body: { text: "" },
      },
    ],
  },
];

export const kindInfo = (kind?: string) => DOC_KINDS.find((k) => k.kind === kind) ?? DOC_KINDS[0]!;
