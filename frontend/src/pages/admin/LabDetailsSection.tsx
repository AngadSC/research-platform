import { useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { InstitutionInput } from "@/components/shared/InstitutionInput";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useUpdateLabDetails } from "@/hooks/admin";
import type { InstitutionHit, Lab } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { formValue, Section } from "./common";

const KNOWN = [
  "name",
  "institution_name",
  "department",
  "description",
  "address",
  "contact_email",
  "website",
];

export function LabDetailsSection({ lab }: { lab: Lab }) {
  const update = useUpdateLabDetails(lab.id);
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const form = useRef<HTMLFormElement>(null);

  /** A pick only fills what is empty, so it never overwrites what someone typed. */
  function fillBlanks(hit: InstitutionHit) {
    for (const [name, value] of [
      ["address", hit.address],
      ["website", hit.website],
    ] as const) {
      const field = form.current?.elements.namedItem(name) as HTMLInputElement | null;
      if (field && !field.value && value) field.value = value;
    }
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const v = (k: string) => formValue(fd, k);
    if (!v("name")) return setErrors({ fields: { name: "Enter a lab name" } });
    if (!v("institution_name"))
      return setErrors({ fields: { institution_name: "Enter an institution" } });
    try {
      await update.mutateAsync({
        name: v("name"),
        institution_name: v("institution_name"),
        department: v("department"),
        description: v("description"),
        address: v("address"),
        contact_email: v("contact_email"),
        website: v("website"),
        inventory_enabled: fd.get("inventory_enabled") === "on",
      });
      setErrors({ fields: {} });
      toast.success("Lab details saved");
    } catch (err) {
      setErrors(formErrors(err, KNOWN));
    }
  }

  const f = errors.fields;
  return (
    <Section title="Lab details" description="Shown to everyone in the lab.">
      <form
        ref={form}
        onSubmit={submit}
        noValidate
        aria-label="Lab details"
        className="grid max-w-2xl gap-4"
      >
        <FormField label="Lab name" error={f.name}>
          {(p) => <Input {...p} name="name" defaultValue={lab.name} />}
        </FormField>
        <FormField
          label="Institution"
          error={f.institution_name}
          hint="Choosing University of Alberta adds its starter links under Institution resources."
        >
          {(p) => (
            <InstitutionInput
              {...p}
              name="institution_name"
              defaultValue={lab.institution.name}
              onPick={fillBlanks}
            />
          )}
        </FormField>
        <FormField label="Department" error={f.department}>
          {(p) => <Input {...p} name="department" defaultValue={lab.department} />}
        </FormField>
        <FormField label="Description" error={f.description}>
          {(p) => <Textarea {...p} name="description" rows={3} defaultValue={lab.description} />}
        </FormField>
        <FormField label="Address" error={f.address}>
          {(p) => <Textarea {...p} name="address" rows={2} defaultValue={lab.address} />}
        </FormField>
        <FormField label="Contact email" error={f.contact_email}>
          {(p) => (
            <Input {...p} name="contact_email" type="email" defaultValue={lab.contact_email} />
          )}
        </FormField>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            name="inventory_enabled"
            defaultChecked={lab.inventory_enabled}
            className="mt-0.5"
          />
          <span>
            This is a wet lab (keep an inventory)
            <span className="block text-xs text-muted-foreground">
              Turn off for a dry lab. Inventory and its orders and protocols disappear for everyone
              in the lab until you turn it back on. Nothing is deleted.
            </span>
          </span>
        </label>
        <FormField label="Website" error={f.website}>
          {(p) => <Input {...p} name="website" defaultValue={lab.website} />}
        </FormField>
        <FormError message={errors.form} />
        <Button type="submit" className="justify-self-start" disabled={update.isPending}>
          Save details
        </Button>
      </form>
    </Section>
  );
}
