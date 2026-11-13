import { useId, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";

/** VISION A3: items marked this way are never given to Claude or any other AI tool. */
export const PARTICIPANT_HINT =
  "Names, contact details, ID numbers, faces or voices. Claude and other AI tools will never see this. Leave it off for de-identified data.";

/** Menu item text: marking is one click, removing the mark asks first (`useConfirmUnmark`). */
export const markLabel = (flagged: boolean) =>
  flagged ? "Remove identifying mark" : "Mark as identifying";

/** Accessible name for a "…" trigger that holds only the marking item. */
export const markMenuLabel = (name: string) => `Identifying participants options for ${name}`;

/**
 * Removing the mark lets Claude read the item on its next call, so it is confirmed. Marking runs
 * at once. Call `confirm(flagged, name, run)` from the menu item and render `dialog` once.
 */
export function useConfirmUnmark() {
  const [pending, setPending] = useState<{ name: string; run: () => void } | null>(null);
  const confirm = (flagged: boolean, name: string, run: () => void) =>
    flagged ? setPending({ name, run }) : run();
  const dialog = (
    <Dialog open={!!pending} onOpenChange={(o) => !o && setPending(null)}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Remove identifying mark</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Claude and other AI tools will be able to read {pending?.name} again. Remove the mark?
        </DialogDescription>
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button
            variant="destructive"
            onClick={() => {
              pending?.run();
              setPending(null);
            }}
          >
            Remove mark
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
  return { confirm, dialog };
}

export function ParticipantBadge() {
  return (
    <Badge variant="warning" title={PARTICIPANT_HINT}>
      Identifies participants
    </Badge>
  );
}

export function ParticipantCheckbox({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="flex items-start gap-2 text-sm">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-describedby={`${id}-hint`}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5"
      />
      <div>
        <label htmlFor={id} className="font-medium">
          Identifies participants
        </label>
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {PARTICIPANT_HINT}
        </p>
      </div>
    </div>
  );
}
