import { useRef, useState, type FormEvent } from "react";
import { useParams } from "react-router";
import { toast } from "sonner";
import { StatusPill } from "@/components/training/ComplianceMatrix";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  certificateUrl,
  useMyTraining,
  useTrainingMutations,
  useTrainingRecords,
  useTrainingRequirements,
} from "@/hooks/training";
import { dayText } from "@/lib/ethics";
import { formErrors, type FormErrors } from "@/lib/forms";
import { categoryLabel, validityText } from "@/lib/training";
import { formValue, NativeSelect, Section } from "@/pages/admin/common";
import { TrainingSection } from "@/pages/admin/TrainingSection";
import { useLab } from "@/hooks/workspace";
import { GraduationCap } from "lucide-react";

/** Training: what the lab requires of me, where I stand, and a way to log a completion. */
export function MyTrainingPage() {
  const { labId = "" } = useParams();
  const manager = useLab(labId).data?.my_permissions.includes("manage_lab") ?? false;
  const mine = useMyTraining(labId);
  const requirements = useTrainingRequirements(labId).data ?? [];
  const all = useTrainingRecords(labId).data ?? [];
  const { createRecord, removeRecord, uploadCertificate } = useTrainingMutations(labId);
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const fileRef = useRef<HTMLInputElement>(null);
  const row = mine.data?.members[0];
  const records = all.filter((r) => r.user.id === row?.user.id); // managers receive everyone's
  const required = mine.data?.requirements.filter((r) => row?.cells[r.id]) ?? [];

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const requirement = formValue(fd, "requirement");
    const completed_on = formValue(fd, "completed_on");
    if (!requirement) return setErrors({ fields: { requirement: "Choose a training" } });
    if (!completed_on) return setErrors({ fields: { completed_on: "Enter the date" } });
    try {
      const rec = await createRecord.mutateAsync({
        requirement,
        completed_on,
        expires_on: formValue(fd, "expires_on") || null,
        notes: formValue(fd, "notes"),
      });
      const file = fileRef.current?.files?.[0];
      if (file) await uploadCertificate.mutateAsync({ id: rec.id, file });
      setErrors({ fields: {} });
      form.reset();
      toast.success("Training recorded");
    } catch (err) {
      setErrors(formErrors(err, ["requirement", "completed_on", "expires_on", "notes"]));
    }
  }

  return (
    <>
      <PageHeader
        title="Training"
        description="Trainings the lab requires of you, and your own records. Only you and the PI or lab admins can see them."
      />
      <div className="grid gap-8">
        <Section title="Required trainings" description="Where you stand today.">
          {mine.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : required.length === 0 ? (
            <EmptyState
              icon={GraduationCap}
              title="Nothing required of you"
              description="When the lab adds a required training that applies to you, it will show here."
            />
          ) : (
            <ul className="grid gap-2" aria-label="Required trainings">
              {required.map((r) => {
                const cell = row!.cells[r.id]!;
                return (
                  <li
                    key={r.id}
                    className="flex flex-wrap items-center gap-3 rounded-md border p-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="font-medium">
                        {r.url ? (
                          <a
                            href={r.url}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="underline-offset-4 hover:underline"
                          >
                            {r.name}
                          </a>
                        ) : (
                          r.name
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {categoryLabel(r.category)} · {validityText(r.validity_months)}
                        {cell.expires_on && ` · expires ${dayText(cell.expires_on)}`}
                        {cell.record && (cell.verified ? " · verified" : " · not verified yet")}
                      </div>
                      {r.notes && <p className="text-sm text-muted-foreground">{r.notes}</p>}
                    </div>
                    <StatusPill status={cell.status} />
                  </li>
                );
              })}
            </ul>
          )}
        </Section>

        <Section
          title="Log a completion"
          description="Add the date you finished and, if you have it, your certificate. A PI or lab admin can then verify it."
        >
          <form
            onSubmit={add}
            noValidate
            aria-label="Log a training"
            className="grid max-w-2xl gap-3"
          >
            <FormField label="Training" error={errors.fields.requirement}>
              {(p) => (
                <NativeSelect {...p} name="requirement" defaultValue="">
                  <option value="">Choose...</option>
                  {requirements.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField label="Completed on" error={errors.fields.completed_on}>
                {(p) => <Input {...p} name="completed_on" type="date" />}
              </FormField>
              <FormField
                label="Expires on (optional)"
                error={errors.fields.expires_on}
                hint="Left blank, it is worked out from the training's validity."
              >
                {(p) => <Input {...p} name="expires_on" type="date" />}
              </FormField>
            </div>
            <FormField label="Certificate (optional)">
              {(p) => <input {...p} ref={fileRef} type="file" accept=".pdf,image/*" />}
            </FormField>
            <FormField label="Notes (optional)">
              {(p) => <Input maxLength={2000} {...p} name="notes" />}
            </FormField>
            <FormError message={errors.form} />
            <Button type="submit" className="justify-self-start" disabled={createRecord.isPending}>
              Save record
            </Button>
          </form>
        </Section>

        <Section title="My records">
          {records.length === 0 ? (
            <p className="text-sm text-muted-foreground">No records yet.</p>
          ) : (
            <ul className="grid gap-2" aria-label="My records">
              {records.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-3 rounded-md border p-3">
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{r.requirement_name}</div>
                    <div className="text-xs text-muted-foreground">
                      Completed {dayText(r.completed_on)}
                      {r.expires_on && ` · expires ${dayText(r.expires_on)}`}
                      {r.verified_at
                        ? ` · verified by ${r.verified_by?.display_name || r.verified_by?.email}`
                        : " · not verified"}
                    </div>
                  </div>
                  {r.has_certificate && (
                    <Button variant="outline" size="sm" asChild>
                      <a
                        href={certificateUrl(labId, r.id)}
                        target="_blank"
                        rel="noreferrer noopener"
                      >
                        Certificate
                      </a>
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Delete ${r.requirement_name} record`}
                    disabled={!!r.verified_at}
                    onClick={() =>
                      removeRecord.mutate(r.id, { onError: () => toast.error("Could not delete.") })
                    }
                  >
                    Delete
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Section>
        {manager && <TrainingSection labId={labId} />}
      </div>
    </>
  );
}
