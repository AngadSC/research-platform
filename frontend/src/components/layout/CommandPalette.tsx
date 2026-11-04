import { useEffect, useState } from "react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useCommands, type Command } from "@/lib/commands";

/** Opens on Cmd/Ctrl+K. Add entries with useRegisterCommands (see lib/commands.ts). */
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const commands = useCommands();

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
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Search projects, pages and actions" />
      <CommandList>
        <CommandEmpty>No matches.</CommandEmpty>
        {[...groups].map(([group, items]) => (
          <CommandGroup key={group} heading={group}>
            {items.map(({ id, label, icon: Icon, onSelect }) => (
              <CommandItem
                key={id}
                value={`${group} ${label}`}
                onSelect={() => {
                  setOpen(false);
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
