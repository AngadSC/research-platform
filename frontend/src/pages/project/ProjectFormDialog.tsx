import { useState, type FormEvent } from "react";
import { useParams } from "react-router";
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
import { useMe, useMembers } from "@/hooks/workspace";
import {
  PROJECT_STATUSES,
  personName,
  type Project,
  type ProjectInput,
  type ProjectStatus,
} from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { PROJECT_COLORS, projectColorStyle } from "@/lib/projectColors";
import { STUDY_TYPES } from "@/lib/nav";

const BLANK = "blank";
// `tasks` is how many tasks the template makes (kept in step with projects/templates.py by a
// backend test).
const TEMPLATES: {
  value: NonNullable<ProjectInput["template"]>;
  label: string;
  help: string;
  tasks: number;
}[] = [
  {
    value: "honours_thesis",
    label: "Honours thesis",
    help: "A plan from proposal to final thesis, with deadlines over about nine months.",
    tasks: 9,
  },
  {
    value: "survey_study",
    label: "Survey study",
    help: "A plan from writing the survey to reporting results, over about six months.",
    tasks: 9,
  },
  {
    value: "experiment",
    label: "Experiment or pilot study",
    help: "A plan from design and pilot to running sessions and writing up, over about six months.",
    tasks: 9,
  },
  {
    value: "secondary_data_analysis",
    label: "Secondary data analysis",
    help: "A plan for working with existing data. The Participants step is marked as not needed.",
    tasks: 8,
  },
  {
    value: "thesis_chapter",
    label: "Thesis chapter",
    help: "A plan for one chapter from outline to final draft, with a Drafts folder and more.",
    tasks: 7,
  },
  {
    value: "ra_onboarding",
    label: "RA onboarding",
    help: "Your first month in a lab: training, access, meeting people and agreeing goals.",
    tasks: 8,
  },
  {
    value: "conference_poster",
    label: "Poster for a conference",
    help: "From the poster rules to printing and practising your talk, with a folder for the files.",
    tasks: 8,
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

/** Optional starting team for a new project. You stay a lead; template tasks stay unassigned. */
function TeamPickers(props: {
  labId: string;
  lead: string;
  members: string[];
  onLead: (id: string) => void;
  onMembers: (ids: string[]) => void;
}) {
  const myId = useMe().data?.id;
  const people = (useMembers(props.labId).data ?? []).filter(
    (m) => m.user.id !== myId && m.role !== "viewer", // viewers can't be given project work
  );
  if (people.length === 0) return null;
  return (
    <>
      <FormField label="Lead" hint="Optional. You stay a lead too.">
        {(p) => (
          <Select
            value={props.lead || "none"}
            onValueChange={(v) => props.onLead(v === "none" ? "" : v)}
          >
            <SelectTrigger {...p}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Just me</SelectItem>
              {people.map((m) => (
                <SelectItem key={m.user.id} value={m.user.id}>
                  {personName(m.user)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </FormField>
      <fieldset className="grid gap-2">
        <legend className="text-sm font-medium">Members</legend>
        <p className="text-xs text-muted-foreground">Optional. They join as contributors.</p>
        <div className="grid max-h-32 gap-1.5 overflow-y-auto sm:grid-cols-2">
          {people
            .filter((m) => m.user.id !== props.lead)
            .map((m) => (
              <label
                key={m.user.id}
                className="flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary/10"
              >
                <input
                  type="checkbox"
                  checked={props.members.includes(m.user.id)}
                  onChange={(e) =>
                    props.onMembers(
                      e.target.checked
                        ? [...props.members, m.user.id]
                        : props.members.filter((v) => v !== m.user.id),
                    )
                  }
                />
                {personName(m.user)}
              </label>
            ))}
        </div>
      </fieldset>
    </>
  );
}

/** Create or edit a project. Throws from onSave are shown inline. */
export function ProjectFormDialog({ open, onOpenChange, project, canRetention, onSave }: Props) {
  const [status, setStatus] = useState<ProjectStatus>(project?.status ?? "planning");
  const { labId = "" } = useParams();
  const [template, setTemplate] = useState<string>(BLANK);
  const [lead, setLead] = useState("");
  const [members, setMembers] = useState<string[]>([]);
  const [studyTypes, setStudyTypes] = useState<string[]>(project?.study_types ?? ["human"]);
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [moreOpen, setMoreOpen] = useState(!!(project?.retain_until || project?.retention_note));

  const chosen = project ? undefined : TEMPLATES.find((t) => t.value === template);

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
        study_types: studyTypes as NonNullable<ProjectInput["study_types"]>,
        start_date: String(f.get("start_date") ?? "") || null,
        ...(template !== BLANK && { template: template as ProjectInput["template"] }),
        ...(!project && lead && { lead }),
        ...(!project && members.length > 0 && { members: members.filter((m) => m !== lead) }),
        ...(canRetention && {
          retain_until: String(f.get("retain_until") ?? "") || null,
          retention_note: String(f.get("retention_note") ?? ""),
        }),
      });
      toast.success("Saved");
      onOpenChange(false);
    } catch (err) {
      const e = formErrors(err, [
        "name",
        "description",
        "start_date",
        "retain_until",
        "retention_note",
      ]);
      if (e.fields.retain_until || e.fields.retention_note) setMoreOpen(true);
      setErrors(e);
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
                    <SelectItem value={BLANK} hint="Start empty and add what you need.">
                      Blank project
                    </SelectItem>
                    {TEMPLATES.map((t) => (
                      <SelectItem key={t.value} value={t.value} hint={t.help}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </FormField>
          )}
          {chosen && (
            <p className="-mt-2 text-xs text-muted-foreground">
              {chosen.tasks} tasks will be created; assign them on the Tasks tab.
            </p>
          )}
          {!project && labId && (
            <TeamPickers
              labId={labId}
              lead={lead}
              members={members}
              onLead={setLead}
              onMembers={setMembers}
            />
          )}
          <fieldset className="grid gap-2">
            <legend className="text-sm font-medium">What does this project study?</legend>
            <p className="text-xs text-muted-foreground">
              This sets which pages the project shows: Participants for people, Subjects for
              animals, strains, cell lines and samples. Pick as many as apply.
            </p>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {STUDY_TYPES.map((t) => (
                <label
                  key={t.value}
                  title={t.help}
                  className="flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary/10"
                >
                  <input
                    type="checkbox"
                    checked={studyTypes.includes(t.value)}
                    onChange={(e) =>
                      setStudyTypes((cur) =>
                        e.target.checked ? [...cur, t.value] : cur.filter((v) => v !== t.value),
                      )
                    }
                  />
                  {t.label}
                </label>
              ))}
            </div>
          </fieldset>
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
          <div className="grid gap-3">
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
          </div>
          {canRetention && (
            <details
              className="grid gap-3 rounded-md border px-3 py-2"
              open={moreOpen}
              onToggle={(e) => setMoreOpen(e.currentTarget.open)}
            >
              <summary className="cursor-pointer text-sm font-medium">More options</summary>
              <p className="text-xs text-muted-foreground">
                Retention is how long the lab must keep this project&apos;s records, for example
                under a funder or ethics rule.
              </p>
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
              <FormField label="Retention note" error={errors.fields.retention_note}>
                {(p) => (
                  <Textarea {...p} name="retention_note" defaultValue={project?.retention_note} />
                )}
              </FormField>
            </details>
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
