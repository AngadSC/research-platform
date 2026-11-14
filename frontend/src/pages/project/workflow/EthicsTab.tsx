import { ShieldCheck } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { ApprovalBadge, ExpiryText } from "@/components/ethics/ApprovalBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useApprovals, useSaveApproval } from "@/hooks/ethics";
import { useLab } from "@/hooks/workspace";
import { useProjectApprovals } from "@/hooks/workflow";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { InstitutionLinks } from "@/pages/project/workflow/InstitutionLinks";
import { fail, LocalErrors, NativeSelect, RecordDialog, str } from "@/pages/project/workflow/parts";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import type { EthicsApproval } from "@/lib/api-types";
import { findApprovalNumbers, type FoundApproval } from "@/lib/approvalNumber";

const FIELDS = ["approval_number", "board", "title", "approval_date", "expiry_date", "projects"];

/** Workflow > Ethics (D134): the approvals linked to this project. A new one made here is
 * linked to the project; the lab's rules for who can see or change it (D48, D52, D56) are the
 * server's, so a restricted approval simply does not appear for people it is hidden from. */
export default function EthicsTab({ labId, projectId, project }: ProjectTabProps) {
  const lab = useLab(labId).data;
  const canView = !!lab?.my_permissions.includes("view_ethics");
  const canCreate =
    !!lab?.my_permissions.includes("edit_ethics") &&
    project.my_permissions.includes("edit_content") &&
    project.status !== "archived";
  const oversight = !!lab?.my_permissions.includes("manage_lab");
  const approvals = useProjectApprovals(labId, projectId, canView);
  const save = useSaveApproval(labId);
  const [adding, setAdding] = useState(false);
  const [params] = useSearchParams();
  // `?link=1` comes from "Link an approval" on the Overview
  const [linking, setLinking] = useState(params.get("link") === "1" && canCreate);
  const [prefill, setPrefill] = useState<FoundApproval | null>(null);
  const [preLink, setPreLink] = useState("");
  const [typed, setTyped] = useState("");
  const rows = useMemo(() => approvals.data ?? [], [approvals.data]);
  const labApprovals = useApprovals(labId, canCreate);
  // Numbers already written in the project's name or description, not yet linked here.
  const mentioned = useMemo(
    () =>
      findApprovalNumbers(`${project.name}\n${project.description ?? ""}`).filter(
        (f) => !rows.some((r) => r.approval_number.toLowerCase() === f.number.toLowerCase()),
      ),
    [project.name, project.description, rows],
  );

  /** A number the person has: if the lab already has that approval, offer to link it; else open
   * the new-approval form with the number filled in. */
  function chooseNumber(found: FoundApproval) {
    const same = (labApprovals.data ?? []).find(
      (a) => a.approval_number.toLowerCase() === found.number.toLowerCase(),
    );
    if (same) setPreLink(same.id);
    else setPrefill(found);
  }
  function submitNumber(e: FormEvent) {
    e.preventDefault();
    const number = typed.trim();
    if (!number) return;
    const known = findApprovalNumbers(number)[0];
    chooseNumber(known ?? { number, board: "" });
    setTyped("");
  }
  const shortcut = canCreate ? (
    <div className="grid gap-2 rounded-lg border bg-muted/30 p-3">
      {mentioned.map((f) => (
        <p key={f.number} className="flex flex-wrap items-center gap-2 text-sm">
          <span>
            This project mentions <strong>{[f.board, f.number].filter(Boolean).join(" ")}</strong>.
          </span>
          <Button size="sm" onClick={() => chooseNumber(f)}>
            Use this number
          </Button>
        </p>
      ))}
      <form onSubmit={submitNumber} className="flex flex-wrap items-center gap-2">
        <label htmlFor="approval-number-quick" className="text-sm">
          I have an approval number
        </label>
        <Input
          id="approval-number-quick"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          maxLength={100}
          autoComplete="off"
          placeholder="e.g. Pro00151738"
          className="h-8 w-48"
        />
        <Button type="submit" size="sm" variant="outline" disabled={!typed.trim()}>
          Continue
        </Button>
      </form>
    </div>
  ) : null;

  const add = canCreate ? (
    <span className="flex gap-2">
      <Button variant="outline" onClick={() => setLinking(true)}>
        Link existing
      </Button>
      <Button onClick={() => setAdding(true)}>New approval</Button>
    </span>
  ) : undefined;
  return (
    <div className="grid gap-6">
      <section aria-label="Ethics approvals" className="grid gap-3">
        {shortcut}
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
            description={
              canCreate
                ? "Link an approval the lab already has, or add a new one, so expiry reminders reach the right people."
                : "Only editors can link approvals. Ask the project lead."
            }
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
      {(linking || preLink) && (
        <LinkExisting
          labId={labId}
          projectId={projectId}
          linked={rows}
          initial={preLink}
          onClose={() => {
            setLinking(false);
            setPreLink("");
          }}
        />
      )}
      {(adding || prefill) && (
        <RecordDialog
          title="New ethics approval"
          fields={FIELDS}
          onClose={() => {
            setAdding(false);
            setPrefill(null);
          }}
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
              <FormField label="Approval number" required error={e.approval_number}>
                {(p) => (
                  <Input
                    maxLength={100}
                    {...p}
                    name="approval_number"
                    autoComplete="off"
                    defaultValue={prefill?.number}
                  />
                )}
              </FormField>
              <FormField label="Ethics board" required error={e.board}>
                {(p) => (
                  <Input
                    maxLength={200}
                    {...p}
                    name="board"
                    autoComplete="off"
                    defaultValue={prefill?.board}
                  />
                )}
              </FormField>
              <FormField label="Title" required error={e.title}>
                {(p) => (
                  <Input
                    maxLength={300}
                    {...p}
                    name="title"
                    autoComplete="off"
                    defaultValue={prefill ? project.name : undefined}
                  />
                )}
              </FormField>
              <div className="grid grid-cols-2 gap-3">
                <FormField label="Approval date" required error={e.approval_date}>
                  {(p) => <Input {...p} type="date" name="approval_date" />}
                </FormField>
                <FormField label="Expiry date" required error={e.expiry_date}>
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

/** Link an approval the lab already has. The server keeps the approval's other links as they are. */
function LinkExisting({
  labId,
  projectId,
  linked,
  initial = "",
  onClose,
}: {
  labId: string;
  projectId: string;
  linked: EthicsApproval[];
  initial?: string;
  onClose: () => void;
}) {
  const all = useApprovals(labId);
  const [pick, setPick] = useState(initial);
  const save = useSaveApproval(labId, pick);
  const options = (all.data ?? []).filter((a) => !linked.some((l) => l.id === a.id));
  const chosen = options.find((a) => a.id === pick);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Link an existing approval</DialogTitle>
        <DialogDescription className="sr-only">
          Pick an approval the lab already has.
        </DialogDescription>
        {options.length === 0 && !all.isLoading ? (
          <p className="text-sm text-muted-foreground">
            Every approval you can see is already linked to this project. Use New approval to add
            another.
          </p>
        ) : (
          <FormField label="Approval" required>
            {(p) => (
              <NativeSelect {...p} value={pick} onChange={(e) => setPick(e.target.value)}>
                <option value="">Choose an approval</option>
                {options.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.approval_number}: {a.title}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!chosen || save.isPending}
            onClick={() =>
              save.mutate(
                { projects: [...chosen!.projects.map((p) => p.id), projectId] },
                {
                  onSuccess: () => {
                    toast.success("Approval linked");
                    onClose();
                  },
                  onError: fail,
                },
              )
            }
          >
            Link
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
