import { useEffect, useState } from "react";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import "@blocknote/shadcn/style.css";

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

interface Props {
  /** Read once on mount; remount (change `key`) to load different content. */
  initialContent: Blocks;
  editable: boolean;
  onChange?: (blocks: Blocks) => void;
  label: string;
}

/** The only place BlockNote is used. Stock BlockNote (core, react, shadcn), unmodified. */
export default function RichEditor({ initialContent, editable, onChange, label }: Props) {
  const editor = useCreateBlockNote({
    // BlockNote rejects an empty array; undefined gives one blank paragraph.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    initialContent: initialContent.length ? (initialContent as any) : undefined,
  });
  const dark = useIsDark();
  return (
    <div role="group" aria-label={label} className="rounded-lg border bg-background py-2">
      <BlockNoteView
        editor={editor}
        editable={editable}
        theme={dark ? "dark" : "light"}
        onChange={() => onChange?.(editor.document)}
      />
    </div>
  );
}
