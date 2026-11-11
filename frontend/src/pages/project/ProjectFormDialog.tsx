import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  PROJECT_STATUSES,
  type Project,
  type ProjectInput,
  type ProjectStatus,
} from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { PROJECT_COLORS, projectColorStyle } from "@/lib/projectColors";

const BLANK = "blank";
const TEMPLATES: { value: NonNullable<ProjectInput["template"]>; label: string; help: string }[] = [
  {
    value: "honours_thesis",
    label: "Honours thesis",
    help: "A plan from proposal to final thesis, with deadlines over about nine months.",
  },
  {
    value: "survey_study",
    label: "Survey study",
    help: "A plan from writing the survey to reporting results, over about six months.",
  },
  {
    value: "secondary_data_analysis",
    label: "Secondary data analysis",
    help: "A plan for working with existing data. The Participants step is marked as not needed.",
  },
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Present when editing. */
  project?: Project;
  /** view_retention (pi, lab_admin): without it the retention fields are hidden (D55). */
  canRetention: boolean;
  onSave: (v: ProjectInput) => Promise<unknown>;
}

/** Create or edit a project. Throws from onSave are shown inline. */
export function ProjectFormDialog({ open, onOpenChange, project, canRetention, onSave }: Props) {
  const [status, setStatus] = useState<ProjectStatus>(project?.status ?? "planning");
  const [template, setTemplate] = useState<string>(BLANK);
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const name = String(f.get("name") ?? "").trim();
    if (!name) return setErrors({ fields: { name: "Enter a project name" } });
    setErrors({ fields: {} });
    const color = f.get("color") as ProjectInput["color"] | null;
    try {
      await onSave({
        name,
        ...(color && { color }),
        description: String(f.get("description") ?? ""),
        status,
        start_date: String(f.get("start_date") ?? "") || null,
        ...(template !== BLANK && { template: template as ProjectInput["template"] }),
        ...(canRetention && {
          retain_until: String(f.get("retain_until") ?? "") || null,
          retention_note: String(f.get("retention_note") ?? ""),
        }),
      });
      toast.success("Saved");
      onOpenChange(false);
    } catch (err) {
      setErrors(
        formErrors(err, ["name", "description", "start_date", "retain_until", "retention_note"]),
      );
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">
          {project ? "Edit project" : "New project"}
        </DialogTitle>
        <DialogDescription className="sr-only">Project details</DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-4">
          <FormField label="Name" error={errors.fields.name}>
            {(p) => (
              <Input
                maxLength={200}
                {...p}
                name="name"
                defaultValue={project?.name}
                autoComplete="off"
              />
            )}
          </FormField>
          <fieldset className="grid gap-2">
            <legend className="text-sm font-medium">Colour</legend>
            <div className="flex flex-wrap gap-2.5 p-1">
              {PROJECT_COLORS.map((c) => (
                <label key={c} className="cursor-pointer" style={projectColorStyle(c)}>
                  <input
                    type="radio"
                    name="color"
                    value={c}
                    defaultChecked={project?.color === c}
                    className="peer sr-only"
                  />
                  <span className="sr-only">{c.charAt(0).toUpperCase() + c.slice(1)}</span>
                  <span
                    aria-hidden
                    className="block size-6 rounded-full bg-(--project) ring-offset-2 ring-offset-background peer-checked:ring-2 peer-checked:ring-foreground peer-focus-visible:outline-2 peer-focus-visible:outline-offset-4 peer-focus-visible:outline-ring"
                  />
                </label>
              ))}
            </div>
            {!project && (
              <p className="text-xs text-muted-foreground">
                Leave this and the project gets the colour least used in your lab.
              </p>
            )}
          </fieldset>
          {!project && (
            <FormField label="Start from" hint={TEMPLATES.find((t) => t.value === template)?.help}>
              {(p) => (
                <Select value={template} onValueChange={setTemplate}>
                  <SelectTrigger {...p}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={BLANK}>Blank project</SelectItem>
                    {TEMPLATES.map((t) => (
                      <SelectItem key={t.value} value={t.value}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </FormField>
          )}
          <FormField label="Description" error={errors.fields.description}>
            {(p) => <Textarea {...p} name="description" defaultValue={project?.description} />}
          </FormField>
          <FormField label="Status">
            {(p) => (
              <Select value={status} onValueChange={(v) => setStatus(v as ProjectStatus)}>
                <SelectTrigger {...p}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROJECT_STATUSES.map((s) => (
                    <SelectItem key={s.value} value={s.value}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Start date" error={errors.fields.start_date}>
              {(p) => (
                <Input
                  {...p}
                  type="date"
                  name="start_date"
                  defaultValue={project?.start_date ?? ""}
                />
              )}
            </FormField>
            {canRetention && (
              <FormField label="Keep until" error={errors.fields.retain_until}>
                {(p) => (
                  <Input
                    {...p}
                    type="date"
                    name="retain_until"
                    defaultValue={project?.retain_until ?? ""}
                  />
                )}
              </FormField>
            )}
          </div>
          {canRetention && (
            <FormField label="Retention note" error={errors.fields.retention_note}>
              {(p) => (
                <Textarea {...p} name="retention_note" defaultValue={project?.retention_note} />
              )}
            </FormField>
          )}
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit">Save</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
