import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCreateLab } from "@/hooks/workspace";
import { formErrors, type FormErrors } from "@/lib/forms";

export function CreateLabPage() {
  const create = useCreateLab();
  const navigate = useNavigate();
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const name = String(new FormData(e.currentTarget).get("name") ?? "").trim();
    if (!name) return setErrors({ fields: { name: "Enter a name for your lab" } });
    setErrors({ fields: {} });
    try {
      const lab = await create.mutateAsync({ name });
      toast.success("Lab created");
      void navigate(`/labs/${lab.id}`);
    } catch (err) {
      setErrors(formErrors(err, ["name"]));
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
          {(p) => <Input {...p} name="name" autoComplete="off" />}
        </FormField>
        <FormError message={errors.form} />
        <Button type="submit" className="justify-self-start" disabled={create.isPending}>
          Create lab
        </Button>
      </form>
    </>
  );
}
