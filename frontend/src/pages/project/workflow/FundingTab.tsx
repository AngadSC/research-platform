import { Landmark } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormField } from "@/components/shared/FormField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useAttachments } from "@/hooks/projects";
import { useFunding } from "@/hooks/workflow";
import { personName, type Funding, type FundingInput } from "@/lib/api-types";
import { FUNDING_STATUSES, label, money, WORKFLOW_TONE } from "@/lib/workflow";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { InstitutionLinks } from "@/pages/project/workflow/InstitutionLinks";
import {
  day,
  fail,
  LocalErrors,
  NativeSelect,
  PersonField,
  RecordDialog,
  str,
} from "@/pages/project/workflow/parts";

/** Workflow > Funding (D133). Amounts are shown to, and written by, project leads only. */
export default function FundingTab({ labId, projectId, project }: ProjectTabProps) {
  const { list, create, update, remove } = useFunding(labId, projectId);
  const [editing, setEditing] = useState<Funding | "new" | null>(null);
  const canEdit = project.my_permissions.includes("edit_content");
  const isLead = project.my_permissions.includes("edit_project");

  const cols: Column<Funding>[] = [
    {
      key: "funder",
      header: "Funder",
      cell: (f) => (
        <div>
          <div className="font-medium">{f.funder}</div>
          {f.program && <div className="text-xs text-muted-foreground">{f.program}</div>}
        </div>
      ),
    },
    { key: "no", header: "Award number", cell: (f) => f.award_number || "" },
    ...(isLead
      ? [
          {
            key: "amount",
            header: "Amount",
            cell: (f: Funding) => money(f.amount, f.currency) ?? "",
          },
        ]
      : []),
    {
      key: "dates",
      header: "Dates",
      cell: (f) => (f.start_date || f.end_date ? `${day(f.start_date)} to ${day(f.end_date)}` : ""),
    },
    {
      key: "status",
      header: "Status",
      cell: (f) => (
        <Badge variant={WORKFLOW_TONE[f.status] ?? "secondary"}>
          {label(FUNDING_STATUSES, f.status)}
        </Badge>
      ),
    },
    { key: "holder", header: "Held by", cell: (f) => (f.holder ? personName(f.holder) : "") },
    ...(canEdit
      ? [
          {
            key: "actions",
            header: "Actions",
            className: "text-right",
            cell: (f: Funding) => (
              <div className="flex justify-end gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Edit ${f.funder}`}
                  onClick={() => setEditing(f)}
                >
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove ${f.funder}`}
                  onClick={() =>
                    remove.mutate(f.id, {
                      onSuccess: () => toast.success("Funding removed"),
                      onError: fail,
                    })
                  }
                >
                  Remove
                </Button>
              </div>
            ),
          },
        ]
      : []),
  ];

  const add = canEdit ? <Button onClick={() => setEditing("new")}>Add funding</Button> : undefined;
  return (
    <div className="grid gap-6">
      <section aria-label="Funding" className="grid gap-3">
        {(list.data?.length ?? 0) > 0 && <div className="flex justify-end">{add}</div>}
        <DataTable
          columns={cols}
          rows={list.data ?? []}
          getRowKey={(f) => f.id}
          loading={list.isLoading}
          empty={
            <EmptyState
              icon={Landmark}
              title="No funding recorded yet"
              description="Record the grants and awards behind this project: who funds it, the award number, dates and who holds it."
              action={add}
            />
          }
        />
        {!isLead && (list.data?.length ?? 0) > 0 && (
          <p className="text-xs text-muted-foreground">
            Amounts are visible to project leads only.
          </p>
        )}
      </section>
      <InstitutionLinks
        labId={labId}
        category="funding"
        title="Funding resources at your institution"
      />
      {editing && (
        <FundingDialog
          labId={labId}
          projectId={projectId}
          funding={editing === "new" ? undefined : editing}
          isLead={isLead}
          onClose={() => setEditing(null)}
          onSave={(v) =>
            editing === "new"
              ? create.mutateAsync(v as FundingInput)
              : update.mutateAsync({ id: editing.id, patch: v })
          }
        />
      )}
    </div>
  );
}

const FIELDS = [
  "funder",
  "program",
  "award_number",
  "amount",
  "currency",
  "start_date",
  "end_date",
  "status",
  "holder",
  "notes",
  "attachment",
];

function FundingDialog({
  labId,
  projectId,
  funding,
  isLead,
  onClose,
  onSave,
}: {
  labId: string;
  projectId: string;
  funding?: Funding;
  isLead: boolean;
  onClose: () => void;
  onSave: (v: Partial<FundingInput>) => Promise<unknown>;
}) {
  const files = useAttachments(labId, projectId).list.data ?? [];
  return (
    <RecordDialog
      title={funding ? "Edit funding" : "Add funding"}
      fields={FIELDS}
      onClose={onClose}
      onSubmit={async (f) => {
        const funder = str(f, "funder");
        if (!funder) throw new LocalErrors({ funder: "Enter the funder" });
        const body: Partial<FundingInput> = {
          funder,
          program: str(f, "program"),
          award_number: str(f, "award_number"),
          start_date: str(f, "start_date") || null,
          end_date: str(f, "end_date") || null,
          status: str(f, "status") as FundingInput["status"],
          holder: str(f, "holder") || null,
          notes: str(f, "notes"),
          attachment: str(f, "attachment") || null,
        };
        if (isLead) {
          body.amount = str(f, "amount") || null;
          body.currency = str(f, "currency").toUpperCase() || "CAD";
        }
        await onSave(body);
      }}
    >
      {(e) => (
        <>
          <FormField label="Funder" error={e.funder}>
            {(p) => (
              <Input {...p} name="funder" defaultValue={funding?.funder} autoComplete="off" />
            )}
          </FormField>
          <FormField label="Program or grant name" error={e.program}>
            {(p) => <Input {...p} name="program" defaultValue={funding?.program} />}
          </FormField>
          <FormField label="Grant or award number" error={e.award_number}>
            {(p) => <Input {...p} name="award_number" defaultValue={funding?.award_number} />}
          </FormField>
          {isLead && (
            <div className="grid grid-cols-[1fr_6rem] gap-3">
              <FormField label="Amount" error={e.amount}>
                {(p) => (
                  <Input
                    {...p}
                    name="amount"
                    inputMode="decimal"
                    defaultValue={funding?.amount ?? ""}
                  />
                )}
              </FormField>
              <FormField label="Currency" error={e.currency}>
                {(p) => (
                  <Input
                    {...p}
                    name="currency"
                    maxLength={3}
                    defaultValue={funding?.currency ?? "CAD"}
                  />
                )}
              </FormField>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Start date" error={e.start_date}>
              {(p) => (
                <Input
                  {...p}
                  type="date"
                  name="start_date"
                  defaultValue={funding?.start_date ?? ""}
                />
              )}
            </FormField>
            <FormField label="End date" error={e.end_date}>
              {(p) => (
                <Input {...p} type="date" name="end_date" defaultValue={funding?.end_date ?? ""} />
              )}
            </FormField>
          </div>
          <FormField label="Status" error={e.status}>
            {(p) => (
              <NativeSelect {...p} name="status" defaultValue={funding?.status ?? "applied"}>
                {FUNDING_STATUSES.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <PersonField
            labId={labId}
            name="holder"
            label="PI or holder"
            value={funding?.holder?.id}
            error={e.holder}
          />
          <FormField label="Notes" error={e.notes}>
            {(p) => <Textarea {...p} name="notes" rows={3} defaultValue={funding?.notes} />}
          </FormField>
          <FormField
            label="Attachment (optional)"
            hint="A file already in this project's Files."
            error={e.attachment}
          >
            {(p) => (
              <NativeSelect
                {...p}
                key={files.length}
                name="attachment"
                defaultValue={funding?.attachment?.id ?? ""}
              >
                <option value="">None</option>
                {files.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.original_filename}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
        </>
      )}
    </RecordDialog>
  );
}
