import { useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField, type FieldControlProps } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useMembers } from "@/hooks/workspace";
import { personName } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { cn } from "@/lib/utils";

export const fail = (e: unknown) => toast.error(formErrors(e, []).form ?? "Something went wrong.");

export const day = (iso: string | null | undefined) =>
  iso
    ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { dateStyle: "medium" })
    : "Not set";

/** A native select with the app's input styling (labelled through FormField). */
export function NativeSelect({
  className,
  children,
  ...props
}: React.ComponentProps<"select"> & Partial<FieldControlProps>) {
  return (
    <select
      className={cn(
        "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none aria-[invalid=true]:border-destructive",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export const str = (f: FormData, k: string) => String(f.get(k) ?? "").trim();

/** Lab members for a "person" field. The server checks the person can view the project. */
export function PersonField({
  labId,
  name,
  label,
  value,
  error,
}: {
  labId: string;
  name: string;
  label: string;
  value?: string;
  error?: string;
}) {
  const members = useMembers(labId).data ?? [];
  return (
    <FormField label={label} error={error}>
      {(p) => (
        <NativeSelect
          {...p}
          key={members.length} // options arrive after mount; remount so the saved person is selected
          name={name}
          defaultValue={value ?? ""}
        >
          <option value="">None</option>
          {members.map((m) => (
            <option key={m.user.id} value={m.user.id}>
              {personName(m.user)}
            </option>
          ))}
        </NativeSelect>
      )}
    </FormField>
  );
}

/** Throw from `onSubmit` to show client-side messages under fields. */
export class LocalErrors extends Error {
  local: Record<string, string>;
  constructor(local: Record<string, string>) {
    super("invalid");
    this.local = local;
  }
}

/** A modal form. `onSubmit` gets the form data and throws an ApiError to show its messages
 * under the fields named in `fields`. */
export function RecordDialog({
  title,
  fields,
  onClose,
  onSubmit,
  children,
  notice,
}: {
  title: string;
  fields: string[];
  onClose: () => void;
  onSubmit: (f: FormData) => Promise<unknown>;
  children: (errors: Record<string, string>) => ReactNode;
  notice?: ReactNode;
}) {
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    try {
      await onSubmit(new FormData(e.currentTarget));
      toast.success("Saved");
      onClose();
    } catch (err) {
      setErrors(err instanceof LocalErrors ? { fields: err.local } : formErrors(err, fields));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle className="text-base font-semibold">{title}</DialogTitle>
        <DialogDescription className="sr-only">{title}</DialogDescription>
        {notice}
        <form onSubmit={submit} noValidate className="grid gap-4">
          {children(errors.fields)}
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              Save
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
