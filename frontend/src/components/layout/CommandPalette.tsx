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

interface Props {
  /** Current lab; without one only the static commands show. */
  labId?: string;
  /** Called with the SPA route of a chosen search hit. */
  onGo?: (url: string) => void;
}

/** Opens on Cmd/Ctrl+K. Add entries with useRegisterCommands (see lib/commands.ts). */
export function CommandPalette({ labId, onGo }: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const commands = useCommands();
  const { hits, loading, error } = useLabSearch(open ? labId : undefined, text);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const groups = new Map<string, Command[]>();
  for (const c of commands) {
    const g = c.group ?? "Actions";
    groups.set(g, [...(groups.get(g) ?? []), c]);
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setText("");
      }}
    >
      <CommandInput
        placeholder="Search everything in this lab, or run an action"
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
