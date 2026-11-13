import { Sparkles } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useAssistantReady } from "@/hooks/assistant";
import { groupHits, useLabSearch } from "@/hooks/search";
import { useCommands, type Command } from "@/lib/commands";
import { openAssistant } from "@/lib/assistant";
import { MOD_KEY, OPEN_SEARCH_EVENT } from "@/lib/constants";

interface Props {
  /** Current lab; without one only the static commands show. */
  labId?: string;
  /** Called with the SPA route of a chosen search hit. */
  onGo?: (url: string) => void;
}

/** Registered groups that jump somewhere; shown together under one "Go to" heading, so they never
 * repeat a search group's heading ("Projects", "Documents"). */
const GO_TO_GROUPS = new Set(["Navigate", "Projects", "Documents", "Research", "Workflow"]);

/** Opens on Cmd/Ctrl+K; Cmd/Ctrl+F stays the browser's own find. Add entries with useRegisterCommands (see lib/commands.ts). */
export function CommandPalette({ labId, onGo }: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [selected, setSelected] = useState("");
  const commands = useCommands();
  const assistantReady = useAssistantReady(open ? labId : undefined);
  const ask = text.trim();
  const { hits, loading, error } = useLabSearch(open ? labId : undefined, text);

  // The palette opens from a shortcut or an event, not a dialog trigger, so the dialog has nothing
  // to give focus back to. Remember what had focus before it opened (a layout effect runs before
  // the dialog moves focus) and return it once the dialog has let go (a passive effect), unless
  // what was chosen (the assistant, a form) has already taken focus somewhere else.
  const returnTo = useRef<HTMLElement | null>(null);
  useLayoutEffect(() => {
    if (open && document.activeElement instanceof HTMLElement)
      returnTo.current = document.activeElement;
  }, [open]);
  useEffect(() => {
    if (open) return;
    const el = returnTo.current;
    returnTo.current = null;
    const now = document.activeElement;
    if (el?.isConnected && (!now || now === document.body || now.closest("[cmdk-root]")))
      el.focus();
  }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey) return;
      if (e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
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

  // A search hit and a registered command for the same item (ids end in the item's id) show once,
  // as the hit.
  const hitIds = new Set(hits.map((h) => h.id));
  const groups = new Map<string, Command[]>();
  for (const c of commands) {
    if (hitIds.has(c.id.split(":").pop()!)) continue;
    const g = c.group && GO_TO_GROUPS.has(c.group) ? "Go to" : (c.group ?? "Actions");
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
        placeholder={`Search everything in this lab, or run an action (${MOD_KEY} K)`}
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
        {ask && assistantReady && (
          <CommandGroup heading="Assistant" forceMount>
            <CommandItem
              value="assistant:ask"
              forceMount
              onSelect={() => {
                setOpen(false);
                setText("");
                openAssistant(ask);
              }}
            >
              <Sparkles aria-hidden />
              <span className="min-w-0 truncate">Ask the assistant: &ldquo;{ask}&rdquo;</span>
            </CommandItem>
          </CommandGroup>
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
