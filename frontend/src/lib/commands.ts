import { useEffect, useSyncExternalStore, type ComponentType } from "react";

export interface Command {
  id: string;
  label: string;
  group?: string;
  icon?: ComponentType<{ className?: string }>;
  onSelect: () => void;
}

let commands: Command[] = [];
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

/** Add commands to the palette. Returns an unregister function. */
export function registerCommands(added: Command[]): () => void {
  const ids = new Set(added.map((c) => c.id));
  commands = [...commands.filter((c) => !ids.has(c.id)), ...added];
  emit();
  return () => {
    commands = commands.filter((c) => !ids.has(c.id));
    emit();
  };
}

/** Register for the lifetime of a component. Memoize `added` (useMemo) to avoid re-registering. */
export function useRegisterCommands(added: Command[]) {
  useEffect(() => registerCommands(added), [added]);
}

export function useCommands(): Command[] {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => commands,
  );
}
