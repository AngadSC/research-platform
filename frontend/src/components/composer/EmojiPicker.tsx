import { useEffect, useRef, useState } from "react";
import { EMOJI_GROUPS, searchEmoji } from "@/lib/emoji";
import { cn } from "@/lib/utils";

/** A small emoji panel with search by name, opening above its button. Closes on Escape or when
 * the click lands elsewhere. Nothing is fetched: the set is built in (D255). */
export function EmojiPicker({
  onPick,
  onClose,
}: {
  onPick: (emoji: string) => void;
  onClose: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState(EMOJI_GROUPS[0]!.id);

  useEffect(() => {
    const away = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [onClose]);

  const searching = query.trim() !== "";
  const items = searching
    ? searchEmoji(query)
    : (EMOJI_GROUPS.find((g) => g.id === group)?.items ?? []);

  return (
    <div
      ref={box}
      role="dialog"
      aria-label="Emoji"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}
      className="absolute bottom-full left-0 z-20 mb-1 grid w-72 max-w-[calc(100vw-2rem)] gap-2 rounded-md border bg-popover p-2 text-popover-foreground shadow-md"
    >
      <input
        autoFocus
        type="search"
        aria-label="Search emoji"
        placeholder="Search emoji"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="h-8 rounded-md border border-input bg-background px-2 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      />
      {!searching && (
        <div className="flex flex-wrap gap-1" role="group" aria-label="Emoji groups">
          {EMOJI_GROUPS.map((g) => (
            <button
              key={g.id}
              type="button"
              aria-pressed={g.id === group}
              onClick={() => setGroup(g.id)}
              className={cn(
                "rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                g.id === group && "bg-accent font-semibold text-accent-foreground",
              )}
            >
              {g.label}
            </button>
          ))}
        </div>
      )}
      <div className="grid max-h-44 grid-cols-8 gap-0.5 overflow-y-auto">
        {items.length === 0 && (
          <p className="col-span-8 py-3 text-center text-sm text-muted-foreground">
            No emoji match that.
          </p>
        )}
        {items.map(([emoji, name]) => (
          <button
            key={emoji}
            type="button"
            aria-label={name}
            title={name}
            onClick={() => onPick(emoji)}
            className="flex size-8 items-center justify-center rounded text-lg hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            {emoji}
          </button>
        ))}
      </div>
    </div>
  );
}
