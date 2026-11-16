import { Bug, Download, Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { subjectsExportUrl, useSubjects } from "@/hooks/subjects";
import type { Subject } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { formValue, NativeSelect } from "@/pages/admin/common";

const KINDS = [
  { value: "animal", label: "Animal or cohort", code: "Cage or animal ID", line: "Strain or line" },
  { value: "microbe", label: "Microbial strain", code: "Strain ID", line: "Strain" },
  { value: "cell_line", label: "Cell line", code: "Stock ID", line: "Cell line" },
  { value: "sample", label: "Sample", code: "Sample ID", line: "Type of sample" },
  { value: "other", label: "Other", code: "Label", line: "Line or type" },
] as const;
const STATUSES = [
  { value: "active", label: "Active" },
  { value: "stored", label: "Stored" },
  { value: "finished", label: "Finished" },
  { value: "gone", label: "Gone (died, culled or discarded)" },
];
const FIELDS = [
  "kind",
  "code",
  "species",
  "line",
  "genotype",
  "sex",
  "count",
  "source",
  "start_date",
  "passage",
  "location",
  "status",
  "approval",
  "notes",
];
const kindLabel = (v: string) => KINDS.find((k) => k.value === v)?.label ?? v;

function SubjectDialog({
  subject,
  defaultKind,
  open,
  onClose,
  onSave,
}: {
  subject: Subject | null;
  defaultKind: string;
  open: boolean;
  onClose: () => void;
  onSave: (body: Record<string, unknown>) => Promise<unknown>;
}) {
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [kind, setKind] = useState(subject?.kind ?? defaultKind);
  const meta = KINDS.find((k) => k.value === kind) ?? KINDS[0];
  const animal = kind === "animal";
  const living = kind === "microbe" || kind === "cell_line";

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const v = (k: string) => formValue(fd, k);
    if (!v("code")) return setErrors({ fields: { code: "Give it a label" } });
    try {
      await onSave({
        kind,
        code: v("code"),
        species: v("species"),
        line: v("line"),
        genotype: v("genotype"),
        sex: animal ? v("sex") : "",
        count: Number(v("count")) || 1,
        source: v("source"),
        start_date: v("start_date") || null,
        passage: living ? v("passage") : "",
        location: v("location"),
        status: v("status") || "active",
        approval: v("approval"),
        notes: v("notes"),
      });
      onClose();
    } catch (err) {
      setErrors(formErrors(err, FIELDS));
    }
  }
  const f = errors.fields;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto">
        <DialogTitle className="text-base font-semibold">
          {subject ? `Edit ${subject.code}` : "Add a subject"}
        </DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Use labels, never names that could identify a person. People belong under Participants.
        </DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="What is it?">
              {(p) => (
                <NativeSelect {...p} value={kind} onChange={(e) => setKind(e.target.value)}>
                  {KINDS.map((k) => (
                    <option key={k.value} value={k.value}>
                      {k.label}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <FormField label={meta.code} error={f.code}>
              {(p) => <Input {...p} name="code" maxLength={60} defaultValue={subject?.code} />}
            </FormField>
            <FormField label="Species" error={f.species}>
              {(p) => (
                <Input
                  {...p}
                  name="species"
                  maxLength={120}
                  placeholder="Mus musculus"
                  defaultValue={subject?.species}
                />
              )}
            </FormField>
            <FormField label={meta.line} error={f.line}>
              {(p) => <Input {...p} name="line" maxLength={160} defaultValue={subject?.line} />}
            </FormField>
            <FormField label="Genotype or modification" error={f.genotype}>
              {(p) => (
                <Input {...p} name="genotype" maxLength={300} defaultValue={subject?.genotype} />
              )}
            </FormField>
            {animal && (
              <FormField label="Sex" error={f.sex}>
                {(p) => (
                  <NativeSelect {...p} name="sex" defaultValue={subject?.sex ?? ""}>
                    <option value="">Not recorded</option>
                    <option value="female">Female</option>
                    <option value="male">Male</option>
                    <option value="mixed">Mixed</option>
                  </NativeSelect>
                )}
              </FormField>
            )}
            <FormField label={animal ? "Animals in this cohort" : "How many"} error={f.count}>
              {(p) => (
                <Input
                  {...p}
                  name="count"
                  type="number"
                  min="1"
                  defaultValue={subject?.count ?? 1}
                />
              )}
            </FormField>
            {living && (
              <FormField label={kind === "cell_line" ? "Passage" : "Passage or generation"}>
                {(p) => (
                  <Input {...p} name="passage" maxLength={40} defaultValue={subject?.passage} />
                )}
              </FormField>
            )}
            <FormField label="Source" error={f.source}>
              {(p) => (
                <Input
                  {...p}
                  name="source"
                  maxLength={200}
                  placeholder="Vendor, colleague or collection site"
                  defaultValue={subject?.source}
                />
              )}
            </FormField>
            <FormField label="Date received, born or collected" error={f.start_date}>
              {(p) => (
                <Input
                  {...p}
                  name="start_date"
                  type="date"
                  defaultValue={subject?.start_date ?? ""}
                />
              )}
            </FormField>
            <FormField label="Where it is kept" error={f.location}>
              {(p) => (
                <Input
                  {...p}
                  name="location"
                  maxLength={200}
                  placeholder="Rack 2, cage 4 / freezer B, box 7"
                  defaultValue={subject?.location}
                />
              )}
            </FormField>
            <FormField label="Status">
              {(p) => (
                <NativeSelect {...p} name="status" defaultValue={subject?.status ?? "active"}>
                  {STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
          </div>
          <FormField
            label="Approval number"
            hint="An animal protocol or biosafety approval, if one covers this."
            error={f.approval}
          >
            {(p) => (
              <Input {...p} name="approval" maxLength={120} defaultValue={subject?.approval} />
            )}
          </FormField>
          <FormField label="Notes" error={f.notes}>
            {(p) => <Textarea {...p} name="notes" rows={3} defaultValue={subject?.notes} />}
          </FormField>
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit">Save</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Animals and cohorts, microbial strains, cell lines and samples: what a project studies when it
 * is not people. Participants stays for human studies, with its own rules (D329). */
export default function SubjectsTab({ labId, projectId, project }: ProjectTabProps) {
  const { list, create, update, remove } = useSubjects(labId, projectId);
  const canEdit = project.my_permissions.includes("edit_content") && project.status !== "archived";
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<Subject | null>(null);
  const [adding, setAdding] = useState(false);
  const rows = useMemo(
    () =>
      (list.data ?? []).filter(
        (s) => (!kind || s.kind === kind) && (!status || s.status === status),
      ),
    [list.data, kind, status],
  );
  const total = (list.data ?? []).reduce((n, s) => n + s.count, 0);
  const firstKind = project.study_types.includes("microbial")
    ? "microbe"
    : project.study_types.includes("cell_line")
      ? "cell_line"
      : project.study_types.includes("samples")
        ? "sample"
        : "animal";

  const cols: Column<Subject>[] = [
    { key: "code", header: "Label", cell: (s) => <span className="font-medium">{s.code}</span> },
    { key: "kind", header: "Type", cell: (s) => kindLabel(s.kind) },
    {
      key: "line",
      header: "Species and line",
      cell: (s) => [s.species, s.line].filter(Boolean).join(" · ") || "-",
    },
    { key: "count", header: "Count", cell: (s) => s.count },
    { key: "loc", header: "Kept in", cell: (s) => s.location || "-" },
    { key: "status", header: "Status", cell: (s) => <StatusBadge status={s.status} /> },
    ...(canEdit
      ? [
          {
            key: "actions",
            header: "Actions",
            className: "text-right",
            cell: (s: Subject) => (
              <div className="flex justify-end gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Edit ${s.code}`}
                  onClick={() => setEditing(s)}
                >
                  <Pencil aria-hidden /> Edit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Delete ${s.code}`}
                  className="text-danger-text hover:bg-danger/10 hover:text-danger-text"
                  onClick={() =>
                    remove.mutate(s.id, {
                      onSuccess: () => toast.success("Removed"),
                      onError: (e) => toast.error(formErrors(e, []).form ?? "Could not remove."),
                    })
                  }
                >
                  <Trash2 aria-hidden /> Delete
                </Button>
              </div>
            ),
          },
        ]
      : []),
  ];

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {list.data
            ? `${list.data.length} ${list.data.length === 1 ? "record" : "records"}, ${total} in all.`
            : "Loading"}{" "}
          Keep labels free of anything that could identify a person.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <NativeSelect
            aria-label="Filter by type"
            className="w-44"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          >
            <option value="">All types</option>
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect
            aria-label="Filter by status"
            className="w-36"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">Any status</option>
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label.split(" (")[0]}
              </option>
            ))}
          </NativeSelect>
          <Button variant="outline" asChild>
            <a href={subjectsExportUrl(labId, projectId)} download="subjects.csv">
              <Download aria-hidden /> Export CSV
            </a>
          </Button>
          {canEdit && (
            <Button onClick={() => setAdding(true)}>
              <Plus aria-hidden /> Add subject
            </Button>
          )}
        </div>
      </div>
      <DataTable
        columns={cols}
        rows={rows}
        getRowKey={(s) => s.id}
        loading={list.isLoading}
        empty={
          <EmptyState
            icon={Bug}
            title={list.data?.length ? "Nothing matches those filters" : "No subjects yet"}
            description={
              list.data?.length
                ? "Clear a filter to see the rest."
                : "Record the animals, strains, cell lines or samples this project works with: what they are, where they came from, where they are kept and their status."
            }
            why="A clear record makes methods sections, ethics reports and handovers much easier."
            action={
              canEdit && !list.data?.length ? (
                <Button onClick={() => setAdding(true)}>
                  <Plus aria-hidden /> Add subject
                </Button>
              ) : undefined
            }
          />
        }
      />
      {(adding || editing) && (
        <SubjectDialog
          key={editing?.id ?? "new"}
          subject={editing}
          defaultKind={firstKind}
          open
          onClose={() => {
            setAdding(false);
            setEditing(null);
          }}
          onSave={async (b) => {
            if (editing) await update.mutateAsync({ id: editing.id, patch: b });
            else await create.mutateAsync(b as never);
            toast.success(editing ? "Saved" : "Added");
          }}
        />
      )}
    </div>
  );
}
