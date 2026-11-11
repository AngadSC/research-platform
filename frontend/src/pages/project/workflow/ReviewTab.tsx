import { ClipboardCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormField } from "@/components/shared/FormField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useReviewItems } from "@/hooks/workflow";
import { personName, type ReviewItem, type ReviewItemInput } from "@/lib/api-types";
import { label, REVIEW_STATUSES, WORKFLOW_TONE } from "@/lib/workflow";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { SectionLists } from "@/pages/project/ResearchTab";
import {
  day,
  fail,
  LocalErrors,
  NativeSelect,
  PersonField,
  RecordDialog,
  str,
} from "@/pages/project/workflow/parts";

/** Workflow > Review: sign-off items, then the project's decisions (D138). */
export default function ReviewTab(props: ProjectTabProps) {
  const { labId, projectId, project } = props;
  const { list, create, update, remove } = useReviewItems(labId, projectId);
  const [editing, setEditing] = useState<ReviewItem | "new" | null>(null);
  const canEdit = project.my_permissions.includes("edit_content");

  const cols: Column<ReviewItem>[] = [
    { key: "title", header: "Item", cell: (r) => <span className="font-medium">{r.title}</span> },
    {
      key: "reviewer",
      header: "Reviewer",
      cell: (r) => (r.reviewer ? personName(r.reviewer) : ""),
    },
    {
      key: "status",
      header: "Status",
      cell: (r) => (
        <Badge variant={WORKFLOW_TONE[r.status] ?? "secondary"}>
          {label(REVIEW_STATUSES, r.status)}
        </Badge>
      ),
    },
    { key: "due", header: "Due", cell: (r) => (r.due_date ? day(r.due_date) : "") },
    { key: "notes", header: "Notes", cell: (r) => r.notes },
    ...(canEdit
      ? [
          {
            key: "actions",
            header: "Actions",
            className: "text-right",
            cell: (r: ReviewItem) => (
              <div className="flex justify-end gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Edit ${r.title}`}
                  onClick={() => setEditing(r)}
                >
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove ${r.title}`}
                  onClick={() =>
                    remove.mutate(r.id, {
                      onSuccess: () => toast.success("Review item removed"),
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
  const add = canEdit ? (
    <Button onClick={() => setEditing("new")}>Request a review</Button>
  ) : undefined;

  return (
    <div className="grid gap-8">
      <section aria-label="Review and sign-off" className="grid gap-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold">Review and sign-off</h2>
          {(list.data?.length ?? 0) > 0 && add}
        </div>
        <DataTable
          columns={cols}
          rows={list.data ?? []}
          getRowKey={(r) => r.id}
          loading={list.isLoading}
          empty={
            <EmptyState
              icon={ClipboardCheck}
              title="No review items yet"
              description="Ask a colleague to review or sign off on part of the project, and track where each request stands."
              action={add}
            />
          }
        />
      </section>
      <section className="grid gap-3">
        <h2 className="text-base font-semibold">Decisions</h2>
        <SectionLists {...props} section="review" />
      </section>
      {editing && (
        <RecordDialog
          title={editing === "new" ? "Request a review" : "Edit review item"}
          fields={["title", "reviewer", "status", "due_date", "notes"]}
          onClose={() => setEditing(null)}
          onSubmit={async (f) => {
            const title = str(f, "title");
            if (!title) throw new LocalErrors({ title: "Enter a title" });
            const body: ReviewItemInput = {
              title,
              reviewer: str(f, "reviewer") || null,
              status: str(f, "status") as ReviewItemInput["status"],
              due_date: str(f, "due_date") || null,
              notes: str(f, "notes"),
            };
            if (editing === "new") await create.mutateAsync(body);
            else await update.mutateAsync({ id: editing.id, patch: body });
          }}
        >
          {(e) => {
            const item = editing === "new" ? undefined : editing;
            return (
              <>
                <FormField label="Title" error={e.title}>
                  {(p) => (
                    <Input
                      maxLength={300}
                      {...p}
                      name="title"
                      defaultValue={item?.title}
                      autoComplete="off"
                    />
                  )}
                </FormField>
                <PersonField
                  labId={labId}
                  name="reviewer"
                  label="Reviewer"
                  value={item?.reviewer?.id}
                  error={e.reviewer}
                />
                <FormField label="Status" error={e.status}>
                  {(p) => (
                    <NativeSelect {...p} name="status" defaultValue={item?.status ?? "requested"}>
                      {REVIEW_STATUSES.map(([v, l]) => (
                        <option key={v} value={v}>
                          {l}
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                </FormField>
                <FormField label="Due date" error={e.due_date}>
                  {(p) => (
                    <Input {...p} type="date" name="due_date" defaultValue={item?.due_date ?? ""} />
                  )}
                </FormField>
                <FormField label="Notes" error={e.notes}>
                  {(p) => <Textarea {...p} name="notes" rows={3} defaultValue={item?.notes} />}
                </FormField>
              </>
            );
          }}
        </RecordDialog>
      )}
    </div>
  );
}
