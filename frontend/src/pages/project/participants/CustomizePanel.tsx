import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import type { RegistryView } from "@/hooks/viewPrefs";
import type { RegistryColumn } from "@/lib/api-types";
import { NativeSelect } from "@/pages/project/workflow/parts";

const Check = ({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) => (
  <label className="flex items-start gap-2 text-sm">
    <input
      type="checkbox"
      className="mt-1"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
    />
    <span>
      {label}
      {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
    </span>
  </label>
);

/** Choose what the registry shows. Hidden columns still count toward progress. */
export function CustomizePanel({
  columns,
  view,
  onChange,
  onReset,
  onClose,
}: {
  columns: RegistryColumn[];
  view: RegistryView;
  onChange: (patch: Partial<RegistryView>) => void;
  onReset: () => void;
  onClose: () => void;
}) {
  const toggle = (id: string, show: boolean) =>
    onChange({ hidden: show ? view.hidden.filter((h) => h !== id) : [...view.hidden, id] });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle>Customize view</DialogTitle>
        <DialogDescription>
          Choose what you see here. This only changes your view, and it is remembered for this
          project on this device.
        </DialogDescription>
        <div className="grid gap-4">
          <fieldset className="grid gap-2">
            <legend className="mb-1 text-sm font-medium">Columns</legend>
            {columns.length === 0 && (
              <p className="text-sm text-muted-foreground">No columns yet.</p>
            )}
            {columns.map((c) => (
              <Check
                key={c.id}
                label={c.name}
                checked={!view.hidden.includes(c.id)}
                onChange={(v) => toggle(c.id, v)}
              />
            ))}
          </fieldset>
          <fieldset className="grid gap-2">
            <legend className="mb-1 text-sm font-medium">Show</legend>
            <Check
              label="Totals"
              hint="The Done column and the percent row"
              checked={view.totals}
              onChange={(totals) => onChange({ totals })}
            />
            <Check
              label="Filters"
              hint="Keep the filter row open"
              checked={view.filters}
              onChange={(filters) => onChange({ filters })}
            />
            <Check
              label="Keyboard tips"
              checked={view.help}
              onChange={(help) => onChange({ help })}
            />
          </fieldset>
          <label className="grid gap-1 text-sm font-medium">
            Row spacing
            <NativeSelect
              value={view.density}
              onChange={(e) => onChange({ density: e.target.value as RegistryView["density"] })}
            >
              <option value="comfortable">Comfortable</option>
              <option value="compact">Compact</option>
            </NativeSelect>
          </label>
          <div className="flex justify-between">
            <Button variant="ghost" onClick={onReset}>
              Reset to default
            </Button>
            <Button onClick={onClose}>Done</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
