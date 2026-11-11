import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ComplianceMatrix } from "@/components/training/ComplianceMatrix";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useProjects } from "@/hooks/projects";
import { useCompliance, useTrainingMutations, useTrainingRequirements } from "@/hooks/training";
import type { TrainingRequirementInput } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { APPLIES_TO, categoryLabel, CATEGORIES, ROLES, validityText } from "@/lib/training";
import { formValue, NativeSelect, Section } from "./common";

type AppliesTo = NonNullable<TrainingRequirementInput["applies_to"]>;

/** The Training page, for PIs and lab admins: who has done what, and the list of required trainings (D175, D177). */
export function TrainingSection({ labId }: { labId: string }) {
  const compliance = useCompliance(labId);
  const requirements = useTrainingRequirements(labId).data ?? [];
  const projects = useProjects(labId).data ?? [];
  const { createRequirement, removeRequirement, verify } = useTrainingMutations(labId);
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [applies, setApplies] = useState<AppliesTo>("all");

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const name = formValue(fd, "name");
    const url = formValue(fd, "url");
    const months = formValue(fd, "validity_months");
    if (!name) return setErrors({ fields: { name: "Enter a name" } });
    if (url && !url.startsWith("https://"))
      return setErrors({ fields: { url: "Enter a web address starting with https://" } });
    try {
      await createRequirement.mutateAsync({
        name,
        category: formValue(fd, "category") as TrainingRequirementInput["category"],
        validity_months: months ? Number(months) : null,
        applies_to: applies,
        roles: fd.getAll("roles") as TrainingRequirementInput["roles"],
        projects: fd.getAll("projects").map(String),
        url,
        notes: formValue(fd, "notes"),
      });
      setErrors({ fields: {} });
      setApplies("all");
      form.reset();
      toast.success("Training added");
    } catch (err) {
      setErrors(
        formErrors(err, ["name", "category", "validity_months", "roles", "projects", "url"]),
      );
    }
  }

  return (
    <Section
      title="Lab training"
      description="Required trainings and who has completed them. Members see only their own records."
    >
      {compliance.data ? (
        <ComplianceMatrix
          data={compliance.data}
          onVerify={(id) =>
            verify.mutate(id, {
              onSuccess: () => toast.success("Record verified"),
              onError: () => toast.error("Could not verify."),
            })
          }
        />
      ) : (
        <p className="text-sm text-muted-foreground">
          {compliance.isError ? "Could not load the training overview." : "Loading..."}
        </p>
      )}

      <div className="grid gap-2">
        <h3 className="text-sm font-semibold">Required trainings</h3>
        {requirements.length === 0 && (
          <p className="text-sm text-muted-foreground">
            None yet. Add the trainings your lab requires, for example research ethics or safety.
          </p>
        )}
        {requirements.map((r) => (
          <div key={r.id} className="flex items-start gap-3 rounded-md border p-3">
            <div className="min-w-0 flex-1">
              <div className="font-medium">{r.name}</div>
              <div className="text-xs text-muted-foreground">
                {categoryLabel(r.category)} · {validityText(r.validity_months)} ·{" "}
                {APPLIES_TO.find((a) => a.value === r.applies_to)?.label}
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Delete ${r.name}`}
              onClick={() =>
                removeRequirement.mutate(r.id, {
                  onError: () =>
                    toast.error("Could not delete. A training with records can't be deleted."),
                })
              }
            >
              Delete
            </Button>
          </div>
        ))}
      </div>

      <form
        onSubmit={add}
        noValidate
        aria-label="Add a required training"
        className="grid max-w-2xl gap-3"
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField label="Training name" error={errors.fields.name}>
            {(p) => <Input maxLength={200} {...p} name="name" />}
          </FormField>
          <FormField label="Category" error={errors.fields.category}>
            {(p) => (
              <NativeSelect {...p} name="category" defaultValue="safety">
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField
            label="Valid for (months)"
            error={errors.fields.validity_months}
            hint="Leave blank if it never expires."
          >
            {(p) => <Input {...p} name="validity_months" type="number" min={1} />}
          </FormField>
          <FormField label="Required of">
            {(p) => (
              <NativeSelect
                {...p}
                value={applies}
                onChange={(e) => setApplies(e.target.value as AppliesTo)}
              >
                {APPLIES_TO.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
        </div>
        {applies === "roles" && (
          <fieldset className="flex flex-wrap gap-4 text-sm">
            <legend className="mb-1 text-sm font-medium">Roles</legend>
            {ROLES.map((r) => (
              <label key={r.value} className="flex items-center gap-2">
                <input type="checkbox" name="roles" value={r.value} /> {r.label}
              </label>
            ))}
            {errors.fields.roles && (
              <p role="alert" className="w-full text-xs font-medium text-destructive">
                {errors.fields.roles}
              </p>
            )}
          </fieldset>
        )}
        {applies === "projects" && (
          <fieldset className="grid gap-1 text-sm">
            <legend className="mb-1 text-sm font-medium">Projects</legend>
            {projects.map((p) => (
              <label key={p.id} className="flex items-center gap-2">
                <input type="checkbox" name="projects" value={p.id} /> {p.name}
              </label>
            ))}
            {errors.fields.projects && (
              <p role="alert" className="text-xs font-medium text-destructive">
                {errors.fields.projects}
              </p>
            )}
          </fieldset>
        )}
        <FormField
          label="Link (optional)"
          error={errors.fields.url}
          hint="Where people take it. Must start with https://"
        >
          {(p) => <Input maxLength={500} {...p} name="url" type="url" />}
        </FormField>
        <FormField label="Notes (optional)">
          {(p) => <Input maxLength={2000} {...p} name="notes" />}
        </FormField>
        <FormError message={errors.form} />
        <Button type="submit" className="justify-self-start" disabled={createRequirement.isPending}>
          Add training
        </Button>
      </form>
    </Section>
  );
}
