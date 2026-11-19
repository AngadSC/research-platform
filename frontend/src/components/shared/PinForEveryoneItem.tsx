import { Pin } from "lucide-react";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { usePinForEveryone, useStartHere } from "@/hooks/startHere";

/** Document menu entry: add the document to everyone's "Start here" list, or take it off. */
export function PinForEveryoneItem({ labId, docId }: { labId: string; docId: string }) {
  const { data } = useStartHere(labId);
  const change = usePinForEveryone(labId);
  const pinned = (data ?? []).some((p) => p.id === docId);
  return (
    <DropdownMenuItem
      onSelect={() => change.mutate({ id: docId, action: pinned ? "unpin" : "pin" })}
    >
      {pinned ? "Unpin for everyone" : "Pin for everyone"}
    </DropdownMenuItem>
  );
}

/** A small mark beside the title while the document is on everyone's Start here list. */
export function PinnedMarker({ labId, docId }: { labId: string; docId: string }) {
  const { data } = useStartHere(labId);
  if (!(data ?? []).some((p) => p.id === docId)) return null;
  return (
    <span className="shrink-0 pt-3" title="Pinned for everyone">
      <Pin className="size-4 text-muted-foreground" aria-label="Pinned for everyone" />
    </span>
  );
}
