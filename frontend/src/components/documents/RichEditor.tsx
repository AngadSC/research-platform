import { useEffect, useState } from "react";
import { BlockNoteSchema, defaultInlineContentSpecs, filterSuggestionItems } from "@blocknote/core";
import {
  createReactInlineContentSpec,
  SuggestionMenuController,
  useCreateBlockNote,
} from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import "@blocknote/shadcn/style.css";
import type { Person } from "@/components/composer/RichComposer";
import { cn } from "@/lib/utils";

export type Blocks = unknown[];

function useIsDark() {
  const el = document.documentElement;
  const [dark, setDark] = useState(el.classList.contains("dark"));
  useEffect(() => {
    const mo = new MutationObserver(() => setDark(el.classList.contains("dark")));
    mo.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => mo.disconnect();
  }, [el]);
  return dark;
}

/** D256: an @mention in a document is inline content holding the person's id and the name as it
 * was written. Built with BlockNote's public API only; the editor's own ":" emoji picker is
 * already on by default. Mentions here do not send notifications. */
const Mention = createReactInlineContentSpec(
  {
    type: "mention",
    propSchema: { userId: { default: "" }, name: { default: "Someone" } },
    content: "none",
  },
  {
    render: ({ inlineContent }) => (
      <span className="rounded bg-primary/10 px-1 font-medium text-primary">
        @{inlineContent.props.name}
      </span>
    ),
  },
);
const schema = BlockNoteSchema.create({
  inlineContentSpecs: { ...defaultInlineContentSpecs, mention: Mention },
});

interface Props {
  /** Read once on mount; remount (change `key`) to load different content. */
  initialContent: Blocks;
  editable: boolean;
  onChange?: (blocks: Blocks) => void;
  label: string;
  className?: string;
  /** Who "@" offers: the project's members, or the lab's for a lab-wide document. */
  people?: Person[];
}

/** The only place BlockNote is used: core, react and shadcn only, plus the mention above. */
export default function RichEditor({
  initialContent,
  editable,
  onChange,
  label,
  className,
  people,
}: Props) {
  const editor = useCreateBlockNote({
    schema,
    // BlockNote rejects an empty array; undefined gives one blank paragraph.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    initialContent: initialContent.length ? (initialContent as any) : undefined,
  });
  const dark = useIsDark();
  return (
    <div
      role="group"
      aria-label={label}
      className={cn("rounded-lg border bg-background py-2", className)}
    >
      <BlockNoteView
        editor={editor}
        editable={editable}
        theme={dark ? "dark" : "light"}
        onChange={() => onChange?.(editor.document)}
      >
        {editable && people && (
          <SuggestionMenuController
            triggerCharacter="@"
            getItems={async (query) =>
              filterSuggestionItems(
                people.map((p) => ({
                  title: p.name,
                  onItemClick: () =>
                    editor.insertInlineContent([
                      { type: "mention", props: { userId: p.id, name: p.name } },
                      " ",
                    ]),
                })),
                query,
              )
            }
          />
        )}
      </BlockNoteView>
    </div>
  );
}
