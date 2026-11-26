import { Minus, Undo2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useItemUse } from "@/hooks/admin";
import { useProjects } from "@/hooks/projects";
import type { InventoryItem } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { compatibleUnits, convert, trimNumber } from "@/lib/units";
import { NativeSelect } from "./common";

export const ALERT_TOAST =
  "Now at or below the alert level. PIs, lab admins and the item's owner were notified.";

/** "I used 10 mL of the water": takes it off the item's stock, converting units, and keeps a
 * log anyone can read and the person (or an inventory manager) can undo. */
export function UseStockDialog({
  labId,
  item,
  onClose,
}: {
  labId: string;
  item: InventoryItem | null;
  onClose: () => void;
}) {
  const { log, take, undo } = useItemUse(labId, item?.id);
  const projects = useProjects(labId).data ?? [];
  const [amount, setAmount] = useState("");
  const [unit, setUnit] = useState("");
  const [project, setProject] = useState("");
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [requestId] = useState(() => crypto.randomUUID()); // a new one each time the dialog opens
  if (!item) return null;

  const units = compatibleUnits(item.unit);
  const chosen = unit || item.unit;
  const n = Number(amount);
  const leaves = Number.isFinite(n) && n > 0 ? convert(n, chosen, item.unit) : null;
  const after = leaves === null ? null : Number(item.quantity) - leaves;
  const level = item.low_stock_at == null ? null : Number(item.low_stock_at);
  const crossesAlert =
    level !== null && after !== null && Number(item.quantity) > level && after <= level;

  function submit(e: FormEvent) {
    e.preventDefault();
    setErrors({ fields: {} });
    take.mutate(
      { amount, unit: chosen, project: project || null, note, request_id: requestId },
      {
        onSuccess: () => {
          toast.success(`Took ${amount} ${chosen} of ${item!.name}`);
          // The server tells the PIs, lab admins and the item's owner when stock falls to the level.
          if (crossesAlert) toast.warning(ALERT_TOAST);
          onClose();
        },
        onError: (err) => setErrors(formErrors(err, ["amount", "unit", "project", "note"])),
      },
    );
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogTitle className="text-base font-semibold">Use {item.name}</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          {trimNumber(item.quantity)} {item.unit} in stock. What you take comes off the total, even
          if you count it in a different unit.
        </DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <div className="grid grid-cols-[1fr_8rem] gap-3">
            <FormField label="Amount used" error={errors.fields.amount}>
              {(p) => (
                <Input
                  {...p}
                  type="number"
                  inputMode="decimal"
                  min="0"
                  step="any"
                  autoFocus
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                />
              )}
            </FormField>
            <FormField label="Unit" error={errors.fields.unit}>
              {(p) =>
                units.length > 0 ? (
                  <NativeSelect {...p} value={chosen} onChange={(e) => setUnit(e.target.value)}>
                    {!units.some((u) => u.toLowerCase() === item.unit.toLowerCase()) && (
                      <option value={item.unit}>{item.unit}</option>
                    )}
                    {units.map((u) => (
                      <option key={u} value={u}>
                        {u}
                      </option>
                    ))}
                  </NativeSelect>
                ) : (
                  <Input {...p} value={item.unit || "(none)"} readOnly />
                )
              }
            </FormField>
          </div>
          {after !== null && (
            <p
              role="status"
              className={
                after < 0 ? "text-sm font-medium text-danger-text" : "text-sm text-muted-foreground"
              }
            >
              {after < 0
                ? `That is more than the ${trimNumber(item.quantity)} ${item.unit} in stock.`
                : `Leaves ${trimNumber(after)} ${item.unit}.`}
            </p>
          )}
          <FormField label="For which project? (optional)" error={errors.fields.project}>
            {(p) => (
              <NativeSelect {...p} value={project} onChange={(e) => setProject(e.target.value)}>
                <option value="">The lab in general</option>
                {projects.map((pr) => (
                  <option key={pr.id} value={pr.id}>
                    {pr.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <FormField label="Note (optional)" error={errors.fields.note}>
            {(p) => (
              <Input
                {...p}
                maxLength={300}
                placeholder="Buffer prep, plate 4"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            )}
          </FormField>
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Close
              </Button>
            </DialogClose>
            <Button type="submit" disabled={take.isPending || !amount || (after ?? 0) < 0}>
              <Minus aria-hidden /> Take from stock
            </Button>
          </div>
        </form>
        <section aria-label="Recent uses" className="grid gap-2 border-t pt-3">
          <h3 className="text-sm font-semibold">Recent uses</h3>
          {(log.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing taken yet.</p>
          ) : (
            <ul className="grid gap-1">
              {(log.data ?? []).slice(0, 8).map((u) => (
                <li
                  key={u.id}
                  className="flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm"
                >
                  <span className={u.reversed_at ? "line-through opacity-60" : undefined}>
                    {trimNumber(u.amount)} {u.unit}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                    {u.used_by.display_name || u.used_by.email}
                    {u.project_name && ` · ${u.project_name}`}
                    {u.protocol_name && ` · ${u.protocol_name}`}
                    {u.lot_number && ` · Lot ${u.lot_number}`}
                    {u.note && ` · ${u.note}`} · <RelativeTime value={u.created_at} />
                  </span>
                  {u.can_reverse && (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Undo ${trimNumber(u.amount)} ${u.unit}`}
                      disabled={undo.isPending}
                      onClick={() =>
                        undo.mutate(u, {
                          onSuccess: () => toast.success("Put back"),
                          onError: (err) =>
                            toast.error(formErrors(err, []).form ?? "Could not undo that."),
                        })
                      }
                    >
                      <Undo2 aria-hidden /> Undo
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </DialogContent>
    </Dialog>
  );
}
