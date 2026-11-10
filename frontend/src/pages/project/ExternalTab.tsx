import { Download, Presentation, Sparkles, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAssistantConfig } from "@/hooks/assistant";
import { downloadUrl, useAttachments } from "@/hooks/projects";
import { useExternalOutputs } from "@/hooks/workflow";
import { useLab } from "@/hooks/workspace";
import type { ExternalOutput, ExternalOutputInput } from "@/lib/api-types";
import { openAssistant } from "@/lib/assistant";
import { isHttpUrl } from "@/lib/research";
import { EXTERNAL_TYPES, label } from "@/lib/workflow";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { UploadDialog } from "@/pages/project/UploadDialog";
import {
  day,
  fail,
  LocalErrors,
  NativeSelect,
  RecordDialog,
  str,
} from "@/pages/project/workflow/parts";

const FIELDS = ["title", "type", "date", "place", "url", "attachment"];

/** Opens the assistant with a question ready to send, on the person's own key (no second LLM
 * path, D214). Hidden, not explained, when the lab's AI policy or a missing key rules it out. */
function ConferenceSuggestions({ labId, projectId }: { labId: string; projectId: string }) {
  const { data: cfg } = useAssistantConfig(labId, true);
  const lab = useLab(labId).data;
  if (!cfg?.can_use || !cfg.providers.some((p) => p.has_key)) return null;
  const near = lab?.address || lab?.institution.name;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-sm">
      <p className="min-w-0 flex-1 text-muted-foreground">
        The assistant can suggest conferences for this project. It can get names, dates and links
        wrong, so check each one yourself. Nothing is added here unless you add it.
      </p>
      <Button
        variant="secondary"
        onClick={() =>
          openAssistant(
            `Use project_overview for project_id ${projectId} to find this project's main topic. Then suggest conferences on that topic in three groups: local${near ? ` (near ${near})` : ""}, national and international. Start your answer with the line "Suggestions to verify: these come from an AI and may be wrong, so check each one on the conference's own website." For each one give its name and what it covers and, only if you are sure, the usual time of year, the city and the official website. Say "unknown" instead of guessing. Do not add anything to the project.`,
          )
        }
      >
        <Sparkles aria-hidden /> Suggest conferences
      </Button>
    </div>
  );
}

/** Posters, presentations and conferences. Files stay in the project's permission-checked storage. */
export default function ExternalTab({ labId, projectId, project }: ProjectTabProps) {
  const { list, create, update, remove } = useExternalOutputs(labId, projectId);
  const [editing, setEditing] = useState<ExternalOutput | "new" | null>(null);
  const canEdit = project.my_permissions.includes("edit_content");

  const cols: Column<ExternalOutput>[] = [
    { key: "title", header: "Title", cell: (x) => <span className="font-medium">{x.title}</span> },
    { key: "type", header: "Type", cell: (x) => label(EXTERNAL_TYPES, x.type) },
    { key: "date", header: "Date", cell: (x) => day(x.date) },
    { key: "place", header: "Place", cell: (x) => x.place },
    {
      key: "url",
      header: "Link",
      cell: (x) =>
        x.url && (
          <a
            href={x.url}
            target="_blank"
            rel="noreferrer noopener"
            className="text-primary hover:underline"
          >
            Open link
          </a>
        ),
    },
    {
      key: "file",
      header: "File",
      cell: (x) =>
        x.attachment && (
          <a
            href={downloadUrl(labId, x.attachment.id)}
            download
            aria-label={`Download ${x.attachment.original_filename}`}
            className="inline-flex items-center gap-1 text-primary hover:underline"
          >
            <Download aria-hidden className="size-4" /> {x.attachment.original_filename}
          </a>
        ),
    },
    ...(canEdit
      ? [
          {
            key: "actions",
            header: "Actions",
            className: "text-right",
            cell: (x: ExternalOutput) => (
              <div className="flex justify-end gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Edit ${x.title}`}
                  onClick={() => setEditing(x)}
                >
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove ${x.title}`}
                  onClick={() =>
                    remove.mutate(x.id, {
                      onSuccess: () => toast.success("Removed"),
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

  const add = canEdit ? <Button onClick={() => setEditing("new")}>Add item</Button> : undefined;
  return (
    <section aria-label="External" className="grid gap-3">
      <ConferenceSuggestions labId={labId} projectId={projectId} />
      {(list.data?.length ?? 0) > 0 && <div className="flex justify-end">{add}</div>}
      <DataTable
        columns={cols}
        rows={list.data ?? []}
        getRowKey={(x) => x.id}
        loading={list.isLoading}
        empty={
          <EmptyState
            icon={Presentation}
            title="No posters or talks yet"
            description="Keep a record of the posters, presentations and conferences from this project, with the file and a link."
            action={add}
          />
        }
      />
      {editing && (
        <ExternalDialog
          labId={labId}
          projectId={projectId}
          item={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
          onSave={(v) =>
            editing === "new"
              ? create.mutateAsync(v)
              : update.mutateAsync({ id: editing.id, patch: v })
          }
        />
      )}
    </section>
  );
}

function ExternalDialog({
  labId,
  projectId,
  item,
  onClose,
  onSave,
}: {
  labId: string;
  projectId: string;
  item?: ExternalOutput;
  onClose: () => void;
  onSave: (v: ExternalOutputInput) => Promise<unknown>;
}) {
  const { list, uploadFile } = useAttachments(labId, projectId);
  const files = list.data ?? [];
  const [attachment, setAttachment] = useState(item?.attachment?.id ?? "");
  const [uploading, setUploading] = useState(false);
  return (
    <>
      <RecordDialog
        title={item ? "Edit item" : "Add item"}
        fields={FIELDS}
        onClose={onClose}
        onSubmit={async (f) => {
          const local: Record<string, string> = {};
          if (!str(f, "title")) local.title = "Enter a title";
          if (!str(f, "date")) local.date = "Pick the date";
          if (str(f, "url") && !isHttpUrl(str(f, "url")))
            local.url = "Enter a link starting with http:// or https://";
          if (Object.keys(local).length) throw new LocalErrors(local);
          await onSave({
            title: str(f, "title"),
            type: str(f, "type") as ExternalOutputInput["type"],
            date: str(f, "date"),
            place: str(f, "place"),
            url: str(f, "url"),
            attachment: attachment || null,
          });
        }}
      >
        {(e) => (
          <>
            <FormField label="Title" error={e.title}>
              {(p) => <Input {...p} name="title" defaultValue={item?.title} autoComplete="off" />}
            </FormField>
            <FormField label="Type" error={e.type}>
              {(p) => (
                <NativeSelect {...p} name="type" defaultValue={item?.type ?? "poster"}>
                  {EXTERNAL_TYPES.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <FormField label="Date" error={e.date}>
              {(p) => <Input {...p} type="date" name="date" defaultValue={item?.date} />}
            </FormField>
            <FormField label="Place" hint="For example the city or the venue." error={e.place}>
              {(p) => <Input {...p} name="place" defaultValue={item?.place} />}
            </FormField>
            <FormField label="Link (optional)" error={e.url}>
              {(p) => <Input {...p} type="url" name="url" defaultValue={item?.url} />}
            </FormField>
            <FormField label="File (optional)" error={e.attachment}>
              {(p) => (
                <NativeSelect
                  {...p}
                  value={attachment}
                  onChange={(ev) => setAttachment(ev.target.value)}
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
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="justify-self-start"
              onClick={() => setUploading(true)}
            >
              <Upload aria-hidden /> Upload a file
            </Button>
          </>
        )}
      </RecordDialog>
      <UploadDialog
        open={uploading}
        onOpenChange={setUploading}
        send={async (file, onProgress) => {
          const a = await uploadFile.mutateAsync({ file, onProgress });
          setAttachment(a.id);
        }}
      />
    </>
  );
}
