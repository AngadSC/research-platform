import { useEffect, useState } from "react";
import {
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  Bold,
  Highlighter,
  Italic,
  List,
  ListOrdered,
  Redo2,
  Strikethrough,
  Underline,
  Undo2,
} from "lucide-react";
import {
  type BlockNoteEditor,
  BlockNoteSchema,
  defaultInlineContentSpecs,
  defaultStyleSpecs,
  filterSuggestionItems,
} from "@blocknote/core";
import {
  createReactInlineContentSpec,
  createReactStyleSpec,
  FormattingToolbarController,
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

/** D261: an @mention in a document is inline content holding the person's id and the name as it
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
/** Font family and size, kept as text styles so they travel with the text. */
const FontFamily = createReactStyleSpec(
  { type: "fontFamily", propSchema: "string" },
  {
    render: (props) => <span ref={props.contentRef} style={{ fontFamily: props.value }} />,
  },
);
const FontSize = createReactStyleSpec(
  { type: "fontSize", propSchema: "string" },
  {
    render: (props) => <span ref={props.contentRef} style={{ fontSize: props.value }} />,
  },
);
const schema = BlockNoteSchema.create({
  inlineContentSpecs: { ...defaultInlineContentSpecs, mention: Mention },
  styleSpecs: { ...defaultStyleSpecs, fontFamily: FontFamily, fontSize: FontSize },
});
type Editor = BlockNoteEditor<
  typeof schema.blockSchema,
  typeof schema.inlineContentSchema,
  typeof schema.styleSchema
>;

const FONTS = [
  ["", "Default"],
  ["Georgia, serif", "Serif"],
  ["Arial, Helvetica, sans-serif", "Arial"],
  ["'Times New Roman', Times, serif", "Times New Roman"],
  ["'Courier New', monospace", "Courier New"],
  ["Verdana, sans-serif", "Verdana"],
];
const SIZES = ["", "12px", "14px", "16px", "18px", "24px", "32px"];
const COLORS = [
  "default",
  "gray",
  "brown",
  "red",
  "orange",
  "yellow",
  "green",
  "blue",
  "purple",
  "pink",
];
const BLOCKS = [
  ["paragraph", "Normal text", {}],
  ["heading", "Heading 1", { level: 1 }],
  ["heading", "Heading 2", { level: 2 }],
  ["heading", "Heading 3", { level: 3 }],
  ["quote", "Quote", {}],
] as const;

/** A Google Docs style toolbar above the page: undo and redo, text style, font, size, bold and
 * the rest, colours, alignment and lists. The editor's own floating toolbar still works too. */
function DocToolbar({ editor }: { editor: Editor }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const off = editor.onSelectionChange(() => tick((n) => n + 1));
    const off2 = editor.onChange(() => tick((n) => n + 1));
    return () => {
      off();
      off2();
    };
  }, [editor]);
  const styles = editor.getActiveStyles() as Record<string, unknown>;
  const block = editor.getTextCursorPosition().block;
  const setBlock = (type: string, props: Record<string, unknown> = {}) =>
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    editor.updateBlock(block, { type, props } as any);
  const toggle = (name: "bold" | "italic" | "underline" | "strike") => {
    editor.toggleStyles({ [name]: true });
    editor.focus();
  };
  const setStyle = (name: string, value: string) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const e = editor as any;
    if (value) e.addStyles({ [name]: value });
    else e.removeStyles({ [name]: "" });
    editor.focus();
  };
  const blockKey = `${block.type}${block.type === "heading" ? (block.props as { level: number }).level : ""}`;
  const align = (block.props as { textAlignment?: string }).textAlignment ?? "left";
  const btn = (active: boolean) =>
    `inline-flex size-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none ${active ? "bg-accent" : ""}`;
  const sel = "h-8 rounded-md border bg-background px-1.5 text-sm";
  // Keep the text selected while a button is pressed.
  const keep = (e: React.MouseEvent) => e.preventDefault();
  return (
    <div
      role="toolbar"
      aria-label="Text formatting"
      onMouseDown={(e) => {
        if (!(e.target instanceof HTMLSelectElement)) keep(e);
      }}
      className="sticky top-0 z-10 flex flex-wrap items-center gap-0.5 border-b bg-muted/40 px-2 py-1"
    >
      <button type="button" aria-label="Undo" className={btn(false)} onClick={() => editor.undo()}>
        <Undo2 className="size-4" aria-hidden />
      </button>
      <button type="button" aria-label="Redo" className={btn(false)} onClick={() => editor.redo()}>
        <Redo2 className="size-4" aria-hidden />
      </button>
      <span className="mx-1 h-5 w-px bg-border" aria-hidden />
      <select
        aria-label="Text style"
        className={sel}
        value={
          BLOCKS.find(([t, , p]) => `${t}${"level" in p ? p.level : ""}` === blockKey)?.[1] ??
          "Normal text"
        }
        onChange={(e) => {
          const b = BLOCKS.find(([, label]) => label === e.target.value)!;
          setBlock(b[0], { ...b[2] });
          editor.focus();
        }}
      >
        {BLOCKS.map(([, label]) => (
          <option key={label}>{label}</option>
        ))}
        {!BLOCKS.some(([t, , p]) => `${t}${"level" in p ? p.level : ""}` === blockKey) && (
          <option value="Normal text" hidden />
        )}
      </select>
      <select
        aria-label="Font"
        className={`${sel} w-28`}
        value={String(styles.fontFamily ?? "")}
        onChange={(e) => setStyle("fontFamily", e.target.value)}
      >
        {FONTS.map(([v, label]) => (
          <option key={label} value={v}>
            {label}
          </option>
        ))}
      </select>
      <select
        aria-label="Font size"
        className={`${sel} w-20`}
        value={String(styles.fontSize ?? "")}
        onChange={(e) => setStyle("fontSize", e.target.value)}
      >
        {SIZES.map((v) => (
          <option key={v} value={v}>
            {v ? v.replace("px", "") : "Size"}
          </option>
        ))}
      </select>
      <span className="mx-1 h-5 w-px bg-border" aria-hidden />
      <button
        type="button"
        aria-label="Bold"
        aria-pressed={!!styles.bold}
        className={btn(!!styles.bold)}
        onClick={() => toggle("bold")}
      >
        <Bold className="size-4" aria-hidden />
      </button>
      <button
        type="button"
        aria-label="Italic"
        aria-pressed={!!styles.italic}
        className={btn(!!styles.italic)}
        onClick={() => toggle("italic")}
      >
        <Italic className="size-4" aria-hidden />
      </button>
      <button
        type="button"
        aria-label="Underline"
        aria-pressed={!!styles.underline}
        className={btn(!!styles.underline)}
        onClick={() => toggle("underline")}
      >
        <Underline className="size-4" aria-hidden />
      </button>
      <button
        type="button"
        aria-label="Strikethrough"
        aria-pressed={!!styles.strike}
        className={btn(!!styles.strike)}
        onClick={() => toggle("strike")}
      >
        <Strikethrough className="size-4" aria-hidden />
      </button>
      <label
        className="inline-flex items-center gap-1 text-xs text-muted-foreground"
        title="Text colour"
      >
        <span className="sr-only">Text colour</span>
        <select
          aria-label="Text colour"
          className={`${sel} w-24`}
          value={String(styles.textColor ?? "default")}
          onChange={(e) => setStyle("textColor", e.target.value)}
        >
          {COLORS.map((c) => (
            <option key={c} value={c}>
              {c === "default" ? "Colour" : c}
            </option>
          ))}
        </select>
      </label>
      <label className="inline-flex items-center gap-1" title="Highlight">
        <Highlighter className="size-4 text-muted-foreground" aria-hidden />
        <select
          aria-label="Highlight colour"
          className={`${sel} w-24`}
          value={String(styles.backgroundColor ?? "default")}
          onChange={(e) => setStyle("backgroundColor", e.target.value)}
        >
          {COLORS.map((c) => (
            <option key={c} value={c}>
              {c === "default" ? "None" : c}
            </option>
          ))}
        </select>
      </label>
      <span className="mx-1 h-5 w-px bg-border" aria-hidden />
      {(
        [
          ["left", AlignLeft],
          ["center", AlignCenter],
          ["right", AlignRight],
          ["justify", AlignJustify],
        ] as const
      ).map(([a, Icon]) => (
        <button
          key={a}
          type="button"
          aria-label={`Align ${a}`}
          aria-pressed={align === a}
          className={btn(align === a)}
          onClick={() => (
            editor.updateBlock(block, { props: { textAlignment: a } } as never),
            editor.focus()
          )}
        >
          <Icon className="size-4" aria-hidden />
        </button>
      ))}
      <span className="mx-1 h-5 w-px bg-border" aria-hidden />
      <button
        type="button"
        aria-label="Bulleted list"
        aria-pressed={block.type === "bulletListItem"}
        className={btn(block.type === "bulletListItem")}
        onClick={() => (
          setBlock(block.type === "bulletListItem" ? "paragraph" : "bulletListItem"),
          editor.focus()
        )}
      >
        <List className="size-4" aria-hidden />
      </button>
      <button
        type="button"
        aria-label="Numbered list"
        aria-pressed={block.type === "numberedListItem"}
        className={btn(block.type === "numberedListItem")}
        onClick={() => (
          setBlock(block.type === "numberedListItem" ? "paragraph" : "numberedListItem"),
          editor.focus()
        )}
      >
        <ListOrdered className="size-4" aria-hidden />
      </button>
    </div>
  );
}

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
      {editable && <DocToolbar editor={editor} />}
      <BlockNoteView
        editor={editor}
        editable={editable}
        theme={dark ? "dark" : "light"}
        formattingToolbar={false}
        onChange={() => onChange?.(editor.document)}
      >
        {/* Below the selection: above it, the toolbar covers the "Add a task" button over the editor. */}
        <FormattingToolbarController
          floatingUIOptions={{ useFloatingOptions: { placement: "bottom-start" } }}
        />
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
