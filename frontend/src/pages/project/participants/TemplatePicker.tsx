import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import type { useRegistry } from "@/hooks/participants";
import type { RegistryColumn } from "@/lib/api-types";
import { missingColumns, TEMPLATES } from "@/lib/participantTemplates";
import { cn } from "@/lib/utils";

/** Pick a kind of study and get its usual data columns. Nothing is locked in. */
export function TemplatePicker({
  registry,
  existing,
  onClose,
}: {
  registry: ReturnType<typeof useRegistry>;
  existing: RegistryColumn[];
  onClose: () => void;
}) {
  const [chosen, setChosen] = useState(TEMPLATES[0]!.id);
  const [busy, setBusy] = useState(false);
  const template = TEMPLATES.find((t) => t.id === chosen)!;
  const toAdd = missingColumns(template, existing);

  async function apply() {
    setBusy(true);
    try {
      for (const c of toAdd) await registry.addColumn.mutateAsync({ ...c, applies_to_groups: [] });
      toast.success(`Added ${toAdd.length} column${toAdd.length === 1 ? "" : "s"}`);
      onClose();
    } catch {
      toast.error("Could not add all the columns. The ones that were added are kept.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle>Start from a template</DialogTitle>
        <DialogDescription>
          Pick the kind of study. You get its usual data columns and can change them any time.
        </DialogDescription>
        <div role="radiogroup" aria-label="Kind of study" className="grid gap-2">
          {TEMPLATES.map((t) => (
            <button
              key={t.id}
              type="button"
              role="radio"
              aria-checked={chosen === t.id}
              onClick={() => setChosen(t.id)}
              className={cn(
                "rounded-lg border p-3 text-left hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                chosen === t.id && "border-primary bg-muted",
              )}
            >
              <span className="block text-sm font-medium">{t.name}</span>
              <span className="block text-xs text-muted-foreground">{t.blurb}</span>
            </button>
          ))}
        </div>
        <p className="text-sm text-muted-foreground">
          {toAdd.length === 0
            ? "You already have all of these columns."
            : `Adds: ${toAdd.map((c) => c.name).join(", ")}.`}
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void apply()} disabled={busy || toAdd.length === 0}>
            Add columns
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
