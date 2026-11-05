import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useUpdateLabDetails } from "@/hooks/admin";
import type { Lab } from "@/lib/api-types";
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
      <form onSubmit={submit} noValidate aria-label="Lab details" className="grid max-w-2xl gap-4">
        <FormField label="Lab name" error={f.name}>
          {(p) => <Input {...p} name="name" defaultValue={lab.name} />}
        </FormField>
        <FormField
          label="Institution"
          error={f.institution_name}
          hint="Choosing University of Alberta adds its starter links under Institution resources."
        >
          {(p) => <Input {...p} name="institution_name" defaultValue={lab.institution.name} />}
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
