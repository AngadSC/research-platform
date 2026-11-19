import { toast } from "sonner";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { usePinForEveryone, useStartHere } from "@/hooks/startHere";

/** Document menu entry: add the document to everyone's "Start here" list, or take it off. */
export function PinForEveryoneItem({ labId, docId }: { labId: string; docId: string }) {
  const { data } = useStartHere(labId);
  const change = usePinForEveryone(labId);
  const pinned = (data ?? []).some((p) => p.id === docId);
  return (
    <DropdownMenuItem
      onSelect={() =>
        change.mutate(
          { id: docId, action: pinned ? "unpin" : "pin" },
          {
            onSuccess: () => toast(pinned ? "Unpinned for everyone" : "Pinned for everyone"),
            onError: () => toast.error("Could not change that."),
          },
        )
      }
    >
      {pinned ? "Unpin for everyone" : "Pin for everyone"}
    </DropdownMenuItem>
  );
}
