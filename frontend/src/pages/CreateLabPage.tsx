import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { InstitutionInput } from "@/components/shared/InstitutionInput";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useCreateLab } from "@/hooks/workspace";
import type { InstitutionHit } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";

export function CreateLabPage() {
  const create = useCreateLab();
  const navigate = useNavigate();
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [picked, setPicked] = useState<InstitutionHit>();

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const name = String(fd.get("name") ?? "").trim();
    const institution_name = String(fd.get("institution_name") ?? "").trim();
    const address = String(fd.get("address") ?? "").trim();
    const website = String(fd.get("website") ?? "").trim();
    if (!name) return setErrors({ fields: { name: "Enter a name for your lab" } });
    setErrors({ fields: {} });
    try {
      const lab = await create.mutateAsync({
        name,
        ...(institution_name && { institution_name }),
        ...(address && { address }),
        ...(website && { website }),
      });
      toast.success("Lab created");
      void navigate(`/labs/${lab.id}`);
    } catch (err) {
      setErrors(formErrors(err, ["name", "institution_name", "address", "website"]));
    }
  }

  return (
    <>
      <PageHeader
        title="Create a lab"
        description="You will be the PI and can invite your team next."
      />
      <form onSubmit={submit} noValidate className="grid max-w-sm gap-4">
        <FormField
          label="Lab name"
          hint="For example, the name of your research group."
          error={errors.fields.name}
        >
          {(p) => <Input maxLength={200} {...p} name="name" autoComplete="off" />}
        </FormField>
        <FormField
          label="University (optional)"
          hint="We add your university's ethics and funding forms when we recognise it."
          error={errors.fields.institution_name}
        >
          {(p) => <InstitutionInput {...p} name="institution_name" onPick={setPicked} />}
        </FormField>
        {picked && (
          <div key={picked.id} className="grid gap-4">
            <FormField label="Address (optional)" error={errors.fields.address}>
              {(p) => (
                <Textarea
                  maxLength={1000}
                  {...p}
                  name="address"
                  rows={2}
                  defaultValue={picked.address}
                />
              )}
            </FormField>
            <FormField label="Website (optional)" error={errors.fields.website}>
              {(p) => <Input maxLength={300} {...p} name="website" defaultValue={picked.website} />}
            </FormField>
          </div>
        )}
        <FormError message={errors.form} />
        <Button type="submit" className="justify-self-start" disabled={create.isPending}>
          Create lab
        </Button>
      </form>
    </>
  );
}
