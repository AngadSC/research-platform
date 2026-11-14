import { TriangleAlert, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormField } from "@/components/shared/FormField";
import { LinkedFiles } from "@/components/shared/LinkedFiles";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useRecruitmentEntries, useRecruitmentPlan } from "@/hooks/workflow";
import type { RecruitmentEntry } from "@/lib/api-types";
import { label, PARTICIPANT_WARNING, RECRUITMENT_STATUSES, totals } from "@/lib/workflow";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import {
  day,
  fail,
  LocalErrors,
  NativeSelect,
  RecordDialog,
  str,
} from "@/pages/project/workflow/parts";

/** Only these services hold participant records; the tab links to them but never reads them. */
const PARTICIPANT_PROVIDERS = ["redcap", "qualtrics"];

/** The warning is part of the tab's contract (D136): it stays visible on every state. */
export function ParticipantWarning() {
  return (
    <div
      role="note"
      className="flex items-start gap-3 rounded-lg border border-warning bg-warning/15 px-4 py-3 text-sm"
    >
      <TriangleAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
      <p className="font-medium">{PARTICIPANT_WARNING}.</p>
    </div>
  );
}

/** Workflow > Participants: recruitment counts only. No names, no ids, no contact details. */
export default function ParticipantsTab({ labId, projectId, project }: ProjectTabProps) {
  const { list, create, remove } = useRecruitmentEntries(labId, projectId);
  const { plan, save } = useRecruitmentPlan(labId, projectId);
  const [dialog, setDialog] = useState<"entry" | "plan" | null>(null);
  const canEdit = project.my_permissions.includes("edit_content");
  const entries = list.data ?? [];
  const sums = totals(entries);
  const target = plan.data?.target_enrolment ?? null;

  const cols: Column<RecruitmentEntry>[] = [
    { key: "date", header: "Date", cell: (e) => day(e.entry_date) },
    { key: "status", header: "Status", cell: (e) => label(RECRUITMENT_STATUSES, e.status) },
    { key: "count", header: "Count", cell: (e) => e.count },
    { key: "notes", header: "Notes", cell: (e) => e.notes },
    ...(canEdit
      ? [
          {
            key: "actions",
            header: "Actions",
            className: "text-right",
            cell: (e: RecruitmentEntry) => (
              <Button
                variant="ghost"
                size="sm"
                aria-label={`Remove entry of ${e.count} ${e.status} on ${e.entry_date}`}
                onClick={() =>
                  remove.mutate(e.id, {
                    onSuccess: () => toast.success("Entry removed"),
                    onError: fail,
                  })
                }
              >
                Remove
              </Button>
            ),
          },
        ]
      : []),
  ];
  const add =
    canEdit && project.status !== "archived" ? (
      <Button onClick={() => setDialog("entry")}>Add entry</Button>
    ) : undefined;

  return (
    <div className="grid gap-6">
      <ParticipantWarning />
      <section aria-label="Recruitment summary" className="grid gap-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold">Recruitment</h2>
          {canEdit && (
            <Button variant="outline" size="sm" onClick={() => setDialog("plan")}>
              Edit target and notes
            </Button>
          )}
        </div>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <Tile label="Target enrolment" value={target === null ? "Not set" : String(target)} />
          {RECRUITMENT_STATUSES.map(([k, l]) => (
            <Tile key={k} label={l} value={String(sums[k] ?? 0)} />
          ))}
        </dl>
        {target !== null && target > 0 && (
          <p className="text-sm text-muted-foreground">
            {sums.enrolled} of {target} enrolled (
            {Math.round(((sums.enrolled ?? 0) / target) * 100)}
            %).
          </p>
        )}
        {plan.data?.notes && <p className="text-sm whitespace-pre-wrap">{plan.data.notes}</p>}
      </section>

      <section aria-label="Recruitment log" className="grid gap-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold">Log</h2>
          {entries.length > 0 && add}
        </div>
        <DataTable
          columns={cols}
          rows={entries}
          getRowKey={(e) => e.id}
          loading={list.isLoading}
          empty={
            <EmptyState
              icon={Users}
              title="No recruitment entries yet"
              description={
                canEdit
                  ? "Add a dated entry each time the counts change: how many were screened, enrolled, withdrew or completed."
                  : "Only editors can add entries. Ask the project lead."
              }
              action={add}
            />
          }
        />
      </section>

      <section aria-label="Participant systems" className="grid gap-2">
        <h2 className="text-base font-semibold">REDCap and Qualtrics</h2>
        <p className="text-sm text-muted-foreground">
          Link the project or survey where participant records live. Only its title and settings are
          read, never the records.
        </p>
        <LinkedFiles
          labId={labId}
          projectId={projectId}
          canEdit={canEdit}
          only={PARTICIPANT_PROVIDERS}
        />
      </section>

      {dialog === "entry" && (
        <RecordDialog
          title="Add recruitment entry"
          fields={["entry_date", "status", "count", "notes"]}
          onClose={() => setDialog(null)}
          notice={<ParticipantWarning />}
          onSubmit={async (f) => {
            const local: Record<string, string> = {};
            if (!str(f, "entry_date")) local.entry_date = "Pick a date";
            const count = Number(str(f, "count"));
            if (!str(f, "count") || !Number.isInteger(count) || count < 0)
              local.count = "Enter a whole number, 0 or more";
            if (Object.keys(local).length) throw new LocalErrors(local);
            await create.mutateAsync({
              entry_date: str(f, "entry_date"),
              status: str(f, "status") as RecruitmentEntry["status"],
              count,
              notes: str(f, "notes"),
            });
          }}
        >
          {(e) => (
            <>
              <FormField label="Date" error={e.entry_date}>
                {(p) => (
                  <Input
                    {...p}
                    type="date"
                    name="entry_date"
                    defaultValue={new Date().toLocaleDateString("en-CA")}
                  />
                )}
              </FormField>
              <FormField label="Status" error={e.status}>
                {(p) => (
                  <NativeSelect {...p} name="status" defaultValue="screened">
                    {RECRUITMENT_STATUSES.map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </FormField>
              <FormField
                label="Number of people"
                hint="Added to the running total for this status."
                error={e.count}
              >
                {(p) => <Input {...p} type="number" name="count" min={0} step={1} />}
              </FormField>
              <FormField label="Notes (optional)" error={e.notes}>
                {(p) => <Input {...p} name="notes" maxLength={500} autoComplete="off" />}
              </FormField>
            </>
          )}
        </RecordDialog>
      )}
      {dialog === "plan" && (
        <RecordDialog
          title="Target enrolment and notes"
          fields={["target_enrolment", "notes"]}
          onClose={() => setDialog(null)}
          notice={<ParticipantWarning />}
          onSubmit={async (f) => {
            const raw = str(f, "target_enrolment");
            const n = Number(raw);
            if (raw && (!Number.isInteger(n) || n < 0))
              throw new LocalErrors({ target_enrolment: "Enter a whole number, 0 or more" });
            await save.mutateAsync({
              target_enrolment: raw ? n : null,
              notes: str(f, "notes"),
            });
          }}
        >
          {(e) => (
            <>
              <FormField label="Target enrolment" error={e.target_enrolment}>
                {(p) => (
                  <Input
                    {...p}
                    type="number"
                    name="target_enrolment"
                    min={0}
                    step={1}
                    defaultValue={target ?? ""}
                  />
                )}
              </FormField>
              <FormField label="Notes" error={e.notes}>
                {(p) => (
                  <Textarea
                    maxLength={5000}
                    {...p}
                    name="notes"
                    rows={4}
                    defaultValue={plan.data?.notes ?? ""}
                  />
                )}
              </FormField>
            </>
          )}
        </RecordDialog>
      )}
    </div>
  );
}

function Tile({ label: l, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border px-3 py-2">
      <dt className="text-xs text-muted-foreground">{l}</dt>
      <dd className="text-xl font-semibold">{value}</dd>
    </div>
  );
}
