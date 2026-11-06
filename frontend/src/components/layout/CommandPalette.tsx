import { useEffect, useState } from "react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { groupHits, useLabSearch } from "@/hooks/search";
import { useCommands, type Command } from "@/lib/commands";
import { MOD_KEY, OPEN_SEARCH_EVENT } from "@/lib/constants";

interface Props {
  /** Current lab; without one only the static commands show. */
  labId?: string;
  /** Called with the SPA route of a chosen search hit. */
  onGo?: (url: string) => void;
}

/** True where Ctrl/Cmd+F should stay the browser's own find: text fields, editors and the PDF viewer. */
function wantsNativeFind(t: EventTarget | null) {
  const el = t instanceof Element ? t : null;
  return (
    !!el?.closest("input, textarea, select, [contenteditable]:not([contenteditable=false])") ||
    !!document.querySelector("[data-native-find]")
  );
}

/** Opens on Cmd/Ctrl+K or Cmd/Ctrl+F. Add entries with useRegisterCommands (see lib/commands.ts). */
export function CommandPalette({ labId, onGo }: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [selected, setSelected] = useState("");
  const commands = useCommands();
  const { hits, loading, error } = useLabSearch(open ? labId : undefined, text);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey) return;
      const k = e.key.toLowerCase();
      if (k === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (k === "f" && !wantsNativeFind(e.target)) {
        e.preventDefault();
        setOpen(true);
      }
    };
    const onOpen = () => setOpen(true);
    document.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_SEARCH_EVENT, onOpen);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_SEARCH_EVENT, onOpen);
    };
  }, []);

  // cmdk picks its first item when the text changes, before search hits arrive. Point it at the
  // first hit when they do, so Enter opens it without an arrow press first.
  const firstHit = groupHits(hits)[0]?.[1][0];
  const firstValue = firstHit && `hit:${firstHit.type}:${firstHit.id}`;
  const [seen, setSeen] = useState<string>();
  if (firstValue && firstValue !== seen) {
    setSeen(firstValue);
    setSelected(firstValue);
  }

  const groups = new Map<string, Command[]>();
  for (const c of commands) {
    const g = c.group ?? "Actions";
    groups.set(g, [...(groups.get(g) ?? []), c]);
  }

  return (
    <CommandDialog
      open={open}
      value={selected}
      onValueChange={setSelected}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setText("");
      }}
    >
      <CommandInput
        placeholder={`Search everything in this lab, or run an action (${MOD_KEY} F or ${MOD_KEY} K)`}
        value={text}
        onValueChange={setText}
      />
      <CommandList>
        <CommandEmpty>{loading ? "Searching..." : "No matches."}</CommandEmpty>
        {groupHits(hits).map(([label, items]) => (
          <CommandGroup key={label} heading={label} forceMount>
            {items.map((h) => (
              <CommandItem
                key={`${h.type}:${h.id}`}
                value={`hit:${h.type}:${h.id}`}
                forceMount
                onSelect={() => {
                  setOpen(false);
                  setText("");
                  onGo?.(h.url);
                }}
              >
                <span className="grid min-w-0">
                  <span className="truncate">{h.title}</span>
                  {(h.project || h.snippet) && (
                    <span className="truncate text-xs text-muted-foreground">
                      {[h.project?.name, h.snippet].filter(Boolean).join(" - ")}
                    </span>
                  )}
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
        {error && (
          <p role="alert" className="px-2 py-1.5 text-xs text-muted-foreground">
            Search is unavailable right now. Actions still work.
          </p>
        )}
        {[...groups].map(([group, items]) => (
          <CommandGroup key={group} heading={group}>
            {items.map(({ id, label, icon: Icon, onSelect }) => (
              <CommandItem
                key={id}
                value={`${group} ${label}`}
                onSelect={() => {
                  setOpen(false);
                  setText("");
                  onSelect();
                }}
              >
                {Icon && <Icon />}
                {label}
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
}
