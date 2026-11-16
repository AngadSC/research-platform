import { ChevronRight, Landmark } from "lucide-react";
import { useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormField } from "@/components/shared/FormField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
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
import { FormReader } from "@/components/shared/FormReader";
import { FromDriveButton } from "@/components/shared/FromDriveButton";
import { attachFromDrive } from "@/lib/drive";
import { fillBlank, readForm } from "@/lib/formReader";

/** Workflow > Funding (D133, D226): PIs only, so everyone who reaches this page can edit it. */
export default function FundingTab(props: ProjectTabProps) {
  if (!props.project.my_permissions.includes("access_funding")) {
    return (
      <EmptyState
        icon={Landmark}
        title="Funding is visible to PIs only"
        description="Ask a PI on this project if you need to know how it is funded."
      />
    );
  }
  return <FundingPanel {...props} />;
}

function FundingPanel({ labId, projectId, project }: ProjectTabProps) {
  const { list, create, update, remove } = useFunding(labId, projectId);
  const [params] = useSearchParams();
  // `?new=1` comes from "Add funding" on the Overview: open the form straight away
  const [editing, setEditing] = useState<Funding | "new" | null>(
    params.get("new") === "1" ? "new" : null,
  );

  const add =
    project.status === "archived" ? undefined : (
      <Button onClick={() => setEditing("new")}>Add funding</Button>
    );
  return (
    <div className="grid gap-6">
      <section aria-label="Funding" className="grid gap-3">
        {(list.data?.length ?? 0) === 0 ? (
          list.isLoading ? null : (
            <EmptyState
              icon={Landmark}
              title="No funding recorded yet"
              description="Record the grants and awards behind this project: who funds it, the award number, dates and who holds it."
              action={add}
            />
          )
        ) : (
          <>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="text-sm text-muted-foreground">{fundingSummary(list.data ?? [])}</p>
              {add}
            </div>
            <ul className="grid gap-2" aria-label="Awards">
              {(list.data ?? []).map((f) => (
                <FundingRow
                  key={f.id}
                  funding={f}
                  canEdit={project.status !== "archived"}
                  onEdit={() => setEditing(f)}
                  onRemove={() =>
                    remove.mutate(f.id, {
                      onSuccess: () => toast.success("Funding removed"),
                      onError: fail,
                    })
                  }
                />
              ))}
            </ul>
          </>
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

/** "2 awards · CA$120,000 · next ends Mar 2027": the whole page in one line. */
function fundingSummary(items: Funding[]): string {
  const totals = new Map<string, number>();
  for (const f of items)
    if (f.amount !== null) {
      const cur = f.currency || "CAD";
      totals.set(cur, (totals.get(cur) ?? 0) + Number(f.amount));
    }
  const today = new Date().toLocaleDateString("en-CA");
  const next = items
    .map((f) => f.end_date)
    .filter((d): d is string => !!d && d >= today)
    .sort()[0];
  return [
    `${items.length} ${items.length === 1 ? "award" : "awards"}`,
    ...[...totals].map(([cur, n]) => money(String(n), cur)),
    next ? `next ends ${day(next)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** One award: funder, status and amount on a line; the rest opens underneath. */
function FundingRow({
  funding: f,
  canEdit,
  onEdit,
  onRemove,
}: {
  funding: Funding;
  canEdit: boolean;
  onEdit: () => void;
  onRemove: () => void;
}) {
  const [open, setOpen] = useState(false);
  const details: [string, string][] = [
    ["Program", f.program],
    ["Award number", f.award_number],
    ["Dates", f.start_date || f.end_date ? `${day(f.start_date)} to ${day(f.end_date)}` : ""],
    ["Held by", f.holder ? personName(f.holder) : ""],
    ["Notes", f.notes],
  ].filter((d): d is [string, string] => !!d[1]);
  return (
    <li className="rounded-xl border bg-card">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <ChevronRight
          aria-hidden
          className={cn(
            "size-4 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-90",
          )}
        />
        <span className="min-w-0 flex-1 truncate font-medium">{f.funder}</span>
        <Badge variant={WORKFLOW_TONE[f.status] ?? "secondary"}>
          {label(FUNDING_STATUSES, f.status)}
        </Badge>
        <span className="w-28 text-right text-sm tabular-nums">
          {money(f.amount, f.currency) ?? ""}
        </span>
      </button>
      {open && (
        <div className="grid gap-2 border-t px-3 py-3 pl-10 text-sm">
          {details.length === 0 ? (
            <p className="text-muted-foreground">Nothing else recorded.</p>
          ) : (
            <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1">
              {details.map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          )}
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" aria-label={`Edit ${f.funder}`} onClick={onEdit}>
              Edit
            </Button>
            {canEdit && (
              <Button
                variant="ghost"
                size="sm"
                aria-label={`Remove ${f.funder}`}
                onClick={onRemove}
              >
                Remove
              </Button>
            )}
          </div>
        </div>
      )}
    </li>
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
  const attachBox = useRef<HTMLDivElement>(null);
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
          <FormReader labId={labId} kind="funding" />
          <FormField label="Funder" required error={e.funder}>
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
          <div ref={attachBox}>
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
              uploadFile.mutateAsync({ file, onProgress, piOnly: true }).then(async (a) => {
                setPicked(a.id);
                // Attaching the letter also fills in what can be read from it (blank fields only).
                try {
                  const form = attachBox.current?.closest("form");
                  const filled = form
                    ? fillBlank(form, await readForm(labId, "funding", file))
                    : [];
                  if (filled.length)
                    toast.success(`Filled in from the letter: ${filled.join(", ")}. Check them.`);
                } catch {
                  /* a letter that cannot be read is still attached */
                }
              })
            }
          />
        </>
      )}
    </RecordDialog>
  );
}
