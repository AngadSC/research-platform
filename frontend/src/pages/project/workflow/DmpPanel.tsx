import { CheckCircle2, ExternalLink, FileText, History } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useDmp } from "@/hooks/dmp";
import { useAttachments } from "@/hooks/projects";
import { personName, type Dmp, type DmpInput } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { InstitutionLinks } from "@/pages/project/workflow/InstitutionLinks";
import { day, NativeSelect, str } from "@/pages/project/workflow/parts";

/** The Tri-Agency RDM / DMP Assistant sections (D180), in the order of the template. */
const DMP_SECTIONS = [
  [
    "data_description",
    "Data description",
    "What data will you collect, create or reuse, and how much?",
  ],
  ["collection", "Data collection", "Methods, instruments, file formats and quality control."],
  [
    "documentation",
    "Documentation and metadata",
    "What a stranger needs to understand and reuse the data.",
  ],
  [
    "storage",
    "Storage and backup",
    "Where it lives while the work is active, who can reach it, how it is backed up and secured.",
  ],
  [
    "preservation",
    "Preservation",
    "What is kept after the project, where, for how long, and who pays.",
  ],
  [
    "sharing",
    "Sharing and reuse",
    "What will be shared, in which repository, under what licence or conditions.",
  ],
  [
    "responsibilities",
    "Responsibilities and resources",
    "Who manages the data, and the costs and skills involved.",
  ],
  [
    "ethics_legal",
    "Ethics and legal compliance",
    "Consent, privacy, Indigenous data governance, intellectual property.",
  ],
] as const;

const STATUS: Record<Dmp["status"], [string, BadgeVariant]> = {
  draft: ["Draft", "secondary"],
  submitted: ["Submitted", "info"],
  approved: ["Approved", "success"],
};

/** Workflow > Data: the project's data management plan above the datasets list (D180).
 * Anyone who can view the project reads it, edit_content writes it, leads approve and delete. */
export function DmpPanel({ labId, projectId, project }: ProjectTabProps) {
  const [showHistory, setShowHistory] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const { plan, history, save, approve, remove } = useDmp(labId, projectId, showHistory);
  const canEdit = project.my_permissions.includes("edit_content");
  const isLead = project.my_permissions.includes("edit_project");
  const data = plan.data;
  const [statusLabel, tone] = data ? STATUS[data.status] : STATUS.draft;
  const exists = !!data?.exists;
  const attachment = data?.attachment as Dmp["attachment"] | null | undefined;
  const approver = data?.approved_by as Dmp["approved_by"] | null | undefined;

  const run = (p: Promise<unknown>, ok: string) =>
    p.then(
      () => toast.success(ok),
      (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
    );

  return (
    <section aria-label="Data management plan" className="grid gap-4 rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <FileText className="size-5 text-muted-foreground" aria-hidden />
          <h2 className="text-base font-semibold">Data management plan</h2>
          {plan.isSuccess && (
            <Badge variant={exists ? tone : "outline"}>
              {exists ? statusLabel : "Not started"}
            </Badge>
          )}
        </div>
        {!editing && (
          <div className="flex flex-wrap gap-2">
            {exists && (
              <Button variant="outline" size="sm" onClick={() => setShowHistory((v) => !v)}>
                <History className="size-4" aria-hidden />
                {showHistory ? "Hide history" : "History"}
              </Button>
            )}
            {canEdit && (
              <Button size="sm" onClick={() => setEditing(true)}>
                {exists ? "Edit plan" : "Start plan"}
              </Button>
            )}
            {isLead && exists && data?.status !== "approved" && (
              <Button
                size="sm"
                variant="secondary"
                disabled={approve.isPending}
                onClick={() => run(approve.mutateAsync(), "Plan approved")}
              >
                <CheckCircle2 className="size-4" aria-hidden />
                Approve
              </Button>
            )}
          </div>
        )}
      </div>

      {plan.isError && (
        <p role="alert" className="text-sm text-destructive">
          Could not load the plan.
        </p>
      )}

      {editing && data ? (
        <DmpForm
          labId={labId}
          projectId={projectId}
          plan={data}
          saving={save.isPending}
          onCancel={() => setEditing(false)}
          onSave={async (body) => {
            await save.mutateAsync(body);
            toast.success("Plan saved");
            setEditing(false);
          }}
        />
      ) : (
        data && (
          <>
            <p className="text-sm text-muted-foreground">
              Follows the Tri-Agency Research Data Management Policy and the Portage DMP Assistant
              template.
              {exists && (
                <>
                  {" "}
                  Last reviewed: {day(data.last_reviewed)}.
                  {data.status === "approved" &&
                    approver &&
                    ` Approved by ${personName(approver)}.`}
                </>
              )}
            </p>
            {!exists && (
              <p className="text-sm">
                No plan yet. Funders expect one before data collection starts.
                {!canEdit && " Someone who can edit this project can start it."}
              </p>
            )}
            {exists && (
              <div className="grid gap-2">
                {DMP_SECTIONS.map(([k, title]) => (
                  <details key={k} className="rounded-md border bg-background px-3 py-2">
                    <summary className="cursor-pointer text-sm font-medium">
                      {title}
                      {!data[k] && (
                        <span className="ml-2 text-xs text-muted-foreground">(empty)</span>
                      )}
                    </summary>
                    <p className="mt-2 text-sm whitespace-pre-wrap">
                      {data[k] || "Nothing written yet."}
                    </p>
                  </details>
                ))}
              </div>
            )}
            {(data.external_url || attachment) && (
              <ul className="grid gap-1 text-sm">
                {data.external_url && (
                  <li>
                    <a
                      href={data.external_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline"
                    >
                      External plan
                      <ExternalLink className="size-3.5" aria-hidden />
                      <span className="sr-only">(opens in a new tab)</span>
                    </a>
                  </li>
                )}
                {attachment && <li>Attached file: {attachment.original_filename}</li>}
              </ul>
            )}
            {isLead && exists && (
              <div>
                {confirmDelete ? (
                  <span className="flex flex-wrap items-center gap-2 text-sm">
                    Delete this plan and its history?
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() =>
                        run(remove.mutateAsync(), "Plan deleted").then(() =>
                          setConfirmDelete(false),
                        )
                      }
                    >
                      Yes, delete
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(false)}>
                      Keep
                    </Button>
                  </span>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(true)}>
                    Delete plan
                  </Button>
                )}
              </div>
            )}
          </>
        )
      )}

      {showHistory && (
        <div aria-label="Plan history" className="grid gap-1 border-t pt-3 text-sm">
          <h3 className="font-medium">History</h3>
          {history.isLoading && <p className="text-muted-foreground">Loading...</p>}
          <ol className="grid gap-1">
            {(history.data ?? []).map((r) => {
              const snap = r.snapshot as { status?: string };
              return (
                <li key={r.id} className="flex flex-wrap gap-x-2">
                  <span className="font-medium">Version {r.number}</span>
                  <span className="text-muted-foreground">
                    {personName(r.created_by)} on{" "}
                    {new Date(r.created_at).toLocaleString(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                    {snap.status ? `, ${snap.status}` : ""}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>
      )}

      <InstitutionLinks
        labId={labId}
        category="data_management"
        title="Data management at your institution"
      />
    </section>
  );
}

function DmpForm({
  labId,
  projectId,
  plan,
  saving,
  onSave,
  onCancel,
}: {
  labId: string;
  projectId: string;
  plan: Dmp;
  saving: boolean;
  onSave: (body: DmpInput) => Promise<unknown>;
  onCancel: () => void;
}) {
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const files = useAttachments(labId, projectId).list.data ?? [];
  const attachment = plan.attachment as Dmp["attachment"] | null;

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const body: Record<string, unknown> = {
      status: str(f, "status"),
      last_reviewed: str(f, "last_reviewed") || null,
      external_url: str(f, "external_url"),
      attachment: str(f, "attachment") || null,
    };
    for (const [k] of DMP_SECTIONS) body[k] = String(f.get(k) ?? "");
    try {
      await onSave(body as DmpInput);
    } catch (err) {
      setErrors(
        formErrors(err, [
          ...DMP_SECTIONS.map(([k]) => k),
          "status",
          "last_reviewed",
          "external_url",
          "attachment",
        ]),
      );
    }
  }

  const err = errors.fields;
  return (
    <form onSubmit={submit} className="grid gap-4" noValidate>
      {plan.status === "approved" && (
        <p role="note" className="rounded-md border border-warning bg-warning/15 px-3 py-2 text-sm">
          This plan is approved. Saving a change sets it back to draft until a lead approves it
          again.
        </p>
      )}
      {DMP_SECTIONS.map(([k, title, hint]) => (
        <FormField key={k} label={title} hint={hint} error={err[k]}>
          {(p) => <Textarea {...p} name={k} rows={4} defaultValue={plan[k]} />}
        </FormField>
      ))}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="Status" error={err.status}>
          {(p) => (
            <NativeSelect
              {...p}
              name="status"
              defaultValue={plan.status === "approved" ? "draft" : plan.status}
            >
              <option value="draft">Draft</option>
              <option value="submitted">Submitted</option>
            </NativeSelect>
          )}
        </FormField>
        <FormField label="Last reviewed" error={err.last_reviewed}>
          {(p) => (
            <Input
              {...p}
              type="date"
              name="last_reviewed"
              defaultValue={plan.last_reviewed ?? ""}
            />
          )}
        </FormField>
      </div>
      <FormField
        label="External plan link (optional)"
        hint="For example a DMP Assistant export address."
        error={err.external_url}
      >
        {(p) => (
          <Input
            {...p}
            type="url"
            name="external_url"
            defaultValue={plan.external_url}
            autoComplete="off"
          />
        )}
      </FormField>
      <FormField
        label="Attachment (optional)"
        hint="A file already in this project's Files."
        error={err.attachment}
      >
        {(p) => (
          <NativeSelect
            {...p}
            key={files.length}
            name="attachment"
            defaultValue={attachment?.id ?? ""}
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
      <FormError message={errors.form} />
      <div className="flex gap-2">
        <Button type="submit" disabled={saving}>
          {saving ? "Saving..." : "Save plan"}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
