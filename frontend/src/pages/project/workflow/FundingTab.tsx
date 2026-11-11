import { Landmark } from "lucide-react";
import { useState } from "react";
import { Navigate } from "react-router";
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
import { UploadDialog } from "@/pages/project/UploadDialog";
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
import { FromDriveButton } from "@/components/shared/FromDriveButton";
import { attachFromDrive } from "@/lib/drive";

/** Workflow > Funding (D133, D226): PIs only, so everyone who reaches this page can edit it. */
export default function FundingTab(props: ProjectTabProps) {
  if (!props.project.my_permissions.includes("access_funding")) {
    return <Navigate to="../ethics" replace />;
  }
  return <FundingPanel {...props} />;
}

function FundingPanel({ labId, projectId }: ProjectTabProps) {
  const { list, create, update, remove } = useFunding(labId, projectId);
  const [editing, setEditing] = useState<Funding | "new" | null>(null);

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
    { key: "amount", header: "Amount", cell: (f) => money(f.amount, f.currency) ?? "" },
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
    {
      key: "actions",
      header: "Actions",
      className: "text-right",
      cell: (f) => (
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
  ];

  const add = <Button onClick={() => setEditing("new")}>Add funding</Button>;
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
  onClose,
  onSave,
}: {
  labId: string;
  projectId: string;
  funding?: Funding;
  onClose: () => void;
  onSave: (v: Partial<FundingInput>) => Promise<unknown>;
}) {
  const { list, uploadFile } = useAttachments(labId, projectId);
  const files = list.data ?? [];
  const [uploading, setUploading] = useState(false);
  const [picked, setPicked] = useState<string>();
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
          amount: str(f, "amount") || null,
          currency: str(f, "currency").toUpperCase() || "CAD",
        };
        await onSave(body);
      }}
    >
      {(e) => (
        <>
          <FormField label="Funder" error={e.funder}>
            {(p) => (
              <Input
                maxLength={200}
                {...p}
                name="funder"
                defaultValue={funding?.funder}
                autoComplete="off"
              />
            )}
          </FormField>
          <FormField label="Program or grant name" error={e.program}>
            {(p) => <Input maxLength={300} {...p} name="program" defaultValue={funding?.program} />}
          </FormField>
          <FormField label="Grant or award number" error={e.award_number}>
            {(p) => (
              <Input
                maxLength={100}
                {...p}
                name="award_number"
                defaultValue={funding?.award_number}
              />
            )}
          </FormField>
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
            hint="Once picked here, only PIs can open this file, even if you later remove it from this record. Anyone on the project can open it until then, so use the button below for a private letter."
            error={e.attachment}
          >
            {(p) => (
              <NativeSelect
                {...p}
                key={`${files.length}-${picked}`}
                name="attachment"
                defaultValue={picked ?? funding?.attachment?.id ?? ""}
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
          <div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setUploading(true)}>
                Upload a letter only PIs can open
              </Button>
              <FromDriveButton
                labId={labId}
                label="Letter from Drive"
                onPick={(f) =>
                  attachFromDrive<{ id: string }>(
                    `/api/labs/${labId}/projects/${projectId}/attachments/`,
                    f.id,
                    { pi_only: true },
                  ).then((a) => setPicked(a.id))
                }
              />
            </div>
          </div>
          <UploadDialog
            open={uploading}
            onOpenChange={setUploading}
            send={(file, onProgress) =>
              uploadFile
                .mutateAsync({ file, onProgress, piOnly: true })
                .then((a) => setPicked(a.id))
            }
          />
        </>
      )}
    </RecordDialog>
  );
}
