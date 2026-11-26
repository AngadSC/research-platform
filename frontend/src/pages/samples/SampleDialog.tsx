import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useNextCodes, useSampleActions } from "@/hooks/samples";
import { useMembers } from "@/hooks/workspace";
import type { Sample, SampleInput, SampleKind } from "@/lib/api-types";
import { personName } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { formValue, NativeSelect } from "@/pages/admin/common";
import { KIND_FIELDS, KINDS, STATUSES } from "./common";

const KNOWN = [
  "kind",
  "code",
  "name",
  "description",
  "owner",
  "status",
  "backbone",
  "insert",
  "resistance",
  "tag",
  "species",
  "genotype",
  "sequence",
  "concentration",
  "buffer",
  "made_on",
];

/** Add or edit a sample. Kind comes first; the code is filled in with the next free one. */
export function SampleDialog({
  labId,
  sample,
  open,
  onClose,
  onSaved,
}: {
  labId: string;
  sample: Sample | null;
  open: boolean;
  onClose: () => void;
  onSaved?: (id: string) => void;
}) {
  const { create, update } = useSampleActions(labId);
  const members = useMembers(labId).data ?? [];
  const codes = useNextCodes(labId, open && !sample).data;
  const [kind, setKind] = useState<SampleKind>(sample?.kind ?? "plasmid");
  const [typed, setTyped] = useState<string>();
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  // The suggested code follows the kind until the person types their own.
  const code = typed ?? (sample ? sample.code : (codes?.[kind] ?? ""));
  const fields = KIND_FIELDS[kind];

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const v = (k: string) => formValue(fd, k);
    if (!v("name")) return setErrors({ fields: { name: "Enter a name" } });
    const body: SampleInput = {
      kind,
      name: v("name"),
      description: v("description"),
      status: v("status") as SampleInput["status"],
      owner: v("owner") || undefined,
    };
    if (code.trim()) body.code = code.trim();
    for (const f of fields) {
      if (f.key === "made_on") body.made_on = v("made_on") || null;
      else body[f.key] = v(f.key);
    }
    try {
      const saved = sample
        ? await update.mutateAsync({ id: sample.id, ...body })
        : await create.mutateAsync(body);
      toast.success(sample ? "Sample saved" : "Sample added");
      onClose();
      onSaved?.(saved.id);
    } catch (err) {
      setErrors(formErrors(err, KNOWN));
    }
  }

  const f = errors.fields;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle className="text-base font-semibold">
          {sample ? "Edit sample" : "Add a sample"}
        </DialogTitle>
        <DialogDescription className="sr-only">Sample details</DialogDescription>
        <form key={sample?.id ?? "new"} onSubmit={submit} noValidate className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Kind" error={f.kind}>
              {(p) => (
                <NativeSelect
                  {...p}
                  name="kind"
                  value={kind}
                  disabled={!!sample}
                  onChange={(e) => {
                    setKind(e.target.value as SampleKind);
                    setTyped(undefined);
                  }}
                >
                  {KINDS.map((k) => (
                    <option key={k.value} value={k.value}>
                      {k.label}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <FormField label="Code" error={f.code} hint="Filled in for you. You can change it.">
              {(p) => (
                <Input
                  {...p}
                  name="code"
                  maxLength={32}
                  value={code}
                  onChange={(e) => setTyped(e.target.value)}
                />
              )}
            </FormField>
          </div>
          <FormField label="Name" error={f.name}>
            {(p) => <Input maxLength={200} {...p} name="name" defaultValue={sample?.name} />}
          </FormField>
          <div key={kind} className="grid gap-3 sm:grid-cols-2">
            {fields.map((k) => (
              <div key={k.key} className={k.type === "long" ? "sm:col-span-2" : undefined}>
                <FormField label={k.label} error={f[k.key]}>
                  {(p) =>
                    k.type === "long" ? (
                      <Textarea
                        {...p}
                        name={k.key}
                        rows={3}
                        className="font-mono"
                        defaultValue={sample?.kind === kind ? (sample[k.key] ?? "") : ""}
                      />
                    ) : (
                      <Input
                        {...p}
                        name={k.key}
                        type={k.type === "date" ? "date" : "text"}
                        maxLength={200}
                        defaultValue={(sample?.kind === kind ? sample[k.key] : "") ?? ""}
                      />
                    )
                  }
                </FormField>
              </div>
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Owner" error={f.owner}>
              {(p) => (
                <NativeSelect {...p} name="owner" defaultValue={sample?.owner.id ?? ""}>
                  <option value="">Me</option>
                  {members.map((m) => (
                    <option key={m.id} value={m.user.id}>
                      {personName(m.user)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <FormField label="Status" error={f.status}>
              {(p) => (
                <NativeSelect {...p} name="status" defaultValue={sample?.status ?? "in_use"}>
                  {STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
          </div>
          <FormField label="Description" error={f.description}>
            {(p) => (
              <Textarea
                maxLength={5000}
                {...p}
                name="description"
                rows={3}
                defaultValue={sample?.description}
              />
            )}
          </FormField>
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={create.isPending || update.isPending}>
              Save
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
