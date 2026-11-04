import { Users } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useLab, useUpdateLab } from "@/hooks/workspace";
import { useRegisterCommands } from "@/lib/commands";
import { formErrors, type FormErrors } from "@/lib/forms";
import { roleLabel } from "@/lib/api-types";

function RenameForm({ labId, name }: { labId: string; name: string }) {
  const update = useUpdateLab(labId);
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const next = String(new FormData(e.currentTarget).get("name") ?? "").trim();
    if (!next) return setErrors({ fields: { name: "Enter a name for your lab" } });
    setErrors({ fields: {} });
    try {
      await update.mutateAsync({ name: next });
      toast.success("Saved");
    } catch (err) {
      setErrors(formErrors(err, ["name"]));
    }
  }

  return (
    <form onSubmit={submit} noValidate className="mb-8 grid max-w-sm gap-4">
      <FormField label="Lab name" error={errors.fields.name}>
        {(p) => <Input {...p} name="name" defaultValue={name} autoComplete="off" />}
      </FormField>
      <FormError message={errors.form} />
      <Button type="submit" className="justify-self-start" disabled={update.isPending}>
        Save
      </Button>
    </form>
  );
}

export function LabHomePage() {
  const { labId = "" } = useParams();
  const navigate = useNavigate();
  const { data: lab, error } = useLab(labId);

  useRegisterCommands(
    useMemo(
      () => [
        {
          id: `lab:${labId}:members`,
          label: "Go to lab members",
          group: "Navigate",
          icon: Users,
          onSelect: () => void navigate(`/labs/${labId}/members`),
        },
      ],
      [labId, navigate],
    ),
  );

  if (error) return <FormError message={formErrors(error, []).form} />;
  if (!lab)
    return (
      <div aria-busy="true" aria-label="Loading" className="grid gap-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-48" />
      </div>
    );

  return (
    <>
      <PageHeader
        title={lab.name}
        description={`${lab.institution.name} · You are ${roleLabel(lab.my_role)}`}
        actions={
          <Button asChild variant="outline">
            <Link to={`/labs/${lab.id}/members`}>Members</Link>
          </Button>
        }
      />
      {lab.my_permissions.includes("manage_lab") && <RenameForm labId={lab.id} name={lab.name} />}
    </>
  );
}
