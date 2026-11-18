import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";

/** The "Delete <name>?" check other areas use before a delete, with the red button naming what
 * goes ("Delete entry"). */
export function ConfirmDelete({
  open,
  name,
  noun,
  description,
  pending,
  onConfirm,
  onClose,
}: {
  open: boolean;
  name: string;
  noun: string;
  description: string;
  pending?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Delete {name}?</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          {description}
        </DialogDescription>
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button variant="destructive" disabled={pending} onClick={onConfirm}>
            Delete {noun}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
