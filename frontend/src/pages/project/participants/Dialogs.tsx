import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { useRegistry } from "@/hooks/participants";
import type { RegistryColumn } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import { CATEGORIES, CODES_ONLY, parseCodes } from "@/lib/participants";
import { NativeSelect } from "@/pages/project/workflow/parts";

type Registry = ReturnType<typeof useRegistry>;

const parseGroups = (text: string) =>
  text
    .split(",")
    .map((g) => g.trim())
    .filter(Boolean);

export function AddParticipantsDialog({
  registry,
  onClose,
}: {
  registry: Registry;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [group, setGroup] = useState("");
  const [errors, setErrors] = useState<{ fields: Record<string, string>; form?: string }>({
    fields: {},
  });
  const codes = parseCodes(text);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await registry.addParticipants.mutateAsync({ codes, ...(group ? { group } : {}) });
      toast.success(
        codes.length === 1 ? "Participant added" : `${codes.length} participants added`,
      );
      onClose();
    } catch (err) {
      setErrors(formErrors(err, ["codes", "code", "group"]));
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle>Add participants</DialogTitle>
        <DialogDescription>
          Paste one code per line, or separate them with spaces or commas. {CODES_ONLY}
        </DialogDescription>
        <form onSubmit={(e) => void submit(e)} className="grid gap-3">
          <FormField
            label="Participant codes"
            required
            error={errors.fields.codes ?? errors.fields.code}
          >
            {(p) => (
              <Textarea
                {...p}
                rows={5}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={"P-001\nP-002\nP-003"}
              />
            )}
          </FormField>
          <FormField
            label="Group (optional)"
            hint="For example a home language. Applies to every code above."
            error={errors.fields.group}
          >
            {(p) => (
              <Input
                {...p}
                maxLength={100}
                value={group}
                onChange={(e) => setGroup(e.target.value)}
              />
            )}
          </FormField>
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!codes.length || registry.addParticipants.isPending}>
              {codes.length > 1 ? `Add ${codes.length} participants` : "Add participant"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ColumnsDialog({
  registry,
  columns,
  cellCounts,
  onClose,
}: {
  registry: Registry;
  columns: RegistryColumn[];
  /** How many cells each column holds, so a delete can say what it removes. */
  cellCounts: Record<string, number>;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("other");
  const [groups, setGroups] = useState("");
  const [confirm, setConfirm] = useState<string>();
  const [error, setError] = useState<string>();

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(undefined);
    try {
      await registry.addColumn.mutateAsync({
        name,
        category: category as RegistryColumn["category"],
        applies_to_groups: parseGroups(groups),
      });
      setName("");
      setGroups("");
    } catch (err) {
      const f = formErrors(err, ["name", "applies_to_groups"]);
      setError(f.fields.name ?? f.fields.applies_to_groups ?? f.form);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle>Data columns</DialogTitle>
        <DialogDescription>
          Each column is one piece of data every participant should have.
        </DialogDescription>
        <ul className="grid gap-1">
          {columns.map((c) => (
            <li key={c.id} className="flex items-center justify-between gap-2 text-sm">
              <span>
                {c.name}
                {c.applies_to_groups.length > 0 && (
                  <span className="text-muted-foreground">
                    {" "}
                    · {c.applies_to_groups.join(", ")} only
                  </span>
                )}
              </span>
              {confirm === c.id ? (
                <span className="flex items-center gap-2">
                  <span className="text-xs">Deletes {cellCounts[c.id] ?? 0} cells.</span>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() =>
                      registry.removeColumn.mutate(c.id, {
                        onSuccess: (r) => {
                          toast.success(`Deleted ${c.name} and ${r.cells_removed} cells`);
                          setConfirm(undefined);
                        },
                      })
                    }
                  >
                    Delete {c.name}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirm(undefined)}>
                    Keep
                  </Button>
                </span>
              ) : (
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Remove ${c.name}`}
                  onClick={() => setConfirm(c.id)}
                >
                  Remove
                </Button>
              )}
            </li>
          ))}
        </ul>
        <form onSubmit={(e) => void add(e)} className="grid gap-3 border-t pt-3">
          <FormField label="New column name" required error={error}>
            {(p) => (
              <Input
                {...p}
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            )}
          </FormField>
          <FormField label="Type">
            {(p) => (
              <NativeSelect {...p} value={category} onChange={(e) => setCategory(e.target.value)}>
                {CATEGORIES.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <FormField
            label="Only for these groups (optional)"
            hint="Separate with commas, for example Punjabi, Spanish. Empty means everyone."
          >
            {(p) => <Input {...p} value={groups} onChange={(e) => setGroups(e.target.value)} />}
          </FormField>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Done
            </Button>
            <Button type="submit" disabled={!name.trim() || registry.addColumn.isPending}>
              Add column
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
