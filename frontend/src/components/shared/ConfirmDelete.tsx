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
  verb = "Delete",
  description,
  items,
  pending,
  onConfirm,
  onClose,
}: {
  open: boolean;
  name: string;
  noun: string;
  /** "Remove" for things that leave a list rather than being destroyed. */
  verb?: string;
  description: string;
  /** Bulk delete: the titles that go, first 5 then "and N more". */
  items?: string[];
  pending?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">
          {verb} {name}?
        </DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          {description}
        </DialogDescription>
        {items && items.length > 0 && (
          <ul className="list-disc pl-5 text-sm" aria-label="Going to be deleted">
            {items.slice(0, 5).map((t, i) => (
              <li key={i} className="truncate">
                {t}
              </li>
            ))}
            {items.length > 5 && (
              <li className="list-none text-muted-foreground">and {items.length - 5} more</li>
            )}
          </ul>
        )}
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button variant="destructive" disabled={pending} onClick={onConfirm}>
            {verb} {noun}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
