import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { ApprovalBadge, ExpiryText } from "@/components/ethics/ApprovalBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useSaveApproval } from "@/hooks/ethics";
import { useLab } from "@/hooks/workspace";
import { useProjectApprovals } from "@/hooks/workflow";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { InstitutionLinks } from "@/pages/project/workflow/InstitutionLinks";
import { LocalErrors, RecordDialog, str } from "@/pages/project/workflow/parts";

const FIELDS = ["approval_number", "board", "title", "approval_date", "expiry_date", "projects"];

/** Workflow > Ethics (D134): the approvals linked to this project. A new one made here is
 * linked to the project; the lab's rules for who can see or change it (D48, D52, D56) are the
 * server's, so a restricted approval simply does not appear for people it is hidden from. */
export default function EthicsTab({ labId, projectId, project }: ProjectTabProps) {
  const lab = useLab(labId).data;
  const canView = !!lab?.my_permissions.includes("view_ethics");
  const canCreate =
    !!lab?.my_permissions.includes("edit_ethics") &&
    project.my_permissions.includes("edit_content");
  const oversight = !!lab?.my_permissions.includes("manage_lab");
  const approvals = useProjectApprovals(labId, projectId, canView);
  const save = useSaveApproval(labId);
  const [adding, setAdding] = useState(false);
  const rows = approvals.data ?? [];

  const add = canCreate ? <Button onClick={() => setAdding(true)}>New approval</Button> : undefined;
  return (
    <div className="grid gap-6">
      <section aria-label="Ethics approvals" className="grid gap-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            Approvals linked to this project.
            {oversight && (
              <>
                {" "}
                <Link className="text-primary hover:underline" to={`/labs/${labId}/ethics`}>
                  See every approval in the lab
                </Link>
                .
              </>
            )}
          </p>
          {rows.length > 0 && add}
        </div>
        {!canView ? (
          <p className="text-sm text-muted-foreground">
            You don&apos;t have access to ethics approvals in this lab.
          </p>
        ) : rows.length === 0 && !approvals.isLoading ? (
          <EmptyState
            icon={ShieldCheck}
            title="No ethics approvals linked yet"
            description="Link the approvals that cover this project so expiry reminders reach the right people."
            action={add}
          />
        ) : (
          <ul className="grid divide-y rounded-lg border">
            {rows.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <Link to={`/labs/${labId}/ethics/${a.id}`} className="font-medium hover:underline">
                  {a.approval_number}: {a.title}
                  <span className="ml-2 text-xs font-normal text-muted-foreground">{a.board}</span>
                </Link>
                <span className="flex items-center gap-2">
                  <ExpiryText expiry={a.expiry_date} />
                  <ApprovalBadge status={a.status} expiry={a.expiry_date} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <InstitutionLinks
        labId={labId}
        category="ethics"
        title="Ethics resources at your institution"
      />
      {adding && (
        <RecordDialog
          title="New ethics approval"
          fields={FIELDS}
          onClose={() => setAdding(false)}
          onSubmit={async (f) => {
            const local: Record<string, string> = {};
            for (const [k, msg] of [
              ["approval_number", "Enter the approval number"],
              ["board", "Enter the ethics board"],
              ["title", "Enter a title"],
              ["approval_date", "Pick the approval date"],
              ["expiry_date", "Pick the expiry date"],
            ] as const)
              if (!str(f, k)) local[k] = msg;
            if (Object.keys(local).length) throw new LocalErrors(local);
            await save.mutateAsync({
              approval_number: str(f, "approval_number"),
              board: str(f, "board"),
              title: str(f, "title"),
              approval_date: str(f, "approval_date"),
              expiry_date: str(f, "expiry_date"),
              restricted: f.get("restricted") === "on",
              projects: [projectId],
            });
          }}
        >
          {(e) => (
            <>
              <FormField label="Approval number" error={e.approval_number}>
                {(p) => <Input {...p} name="approval_number" autoComplete="off" />}
              </FormField>
              <FormField label="Ethics board" error={e.board}>
                {(p) => <Input {...p} name="board" autoComplete="off" />}
              </FormField>
              <FormField label="Title" error={e.title}>
                {(p) => <Input {...p} name="title" autoComplete="off" />}
              </FormField>
              <div className="grid grid-cols-2 gap-3">
                <FormField label="Approval date" error={e.approval_date}>
                  {(p) => <Input {...p} type="date" name="approval_date" />}
                </FormField>
                <FormField label="Expiry date" error={e.expiry_date}>
                  {(p) => <Input {...p} type="date" name="expiry_date" />}
                </FormField>
              </div>
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" name="restricted" className="mt-1" />
                <span>
                  Restricted
                  <span className="block text-xs text-muted-foreground">
                    Only PIs, lab admins and people who can see this project will see it. Add its
                    files from the approval&apos;s page after saving.
                  </span>
                </span>
              </label>
            </>
          )}
        </RecordDialog>
      )}
    </div>
  );
}
