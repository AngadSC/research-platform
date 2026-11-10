import { FlaskConical } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useInventory, useProtocols } from "@/hooks/admin";
import { personName, type InventoryUsage, type Protocol } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { NativeSelect, str } from "@/pages/project/workflow/parts";

type Reagent = Protocol["reagents"][number];

const qty = (n: string, unit: string) => `${Number(n)} ${unit}`.trim();

/** Workflow > Protocols (D228): recipes for this project, and recording what you used. */
export default function ProtocolsTab({ labId, projectId, project }: ProjectTabProps) {
  const { list, usage, save, remove, use, reverse } = useProtocols(labId, projectId);
  const [editing, setEditing] = useState<Protocol | "new" | null>(null);
  const [using, setUsing] = useState<{ protocol: Protocol; reagent: Reagent } | null>(null);
  const canEdit = project.my_permissions.includes("edit_content");
  const fail = (e: unknown) => toast.error(formErrors(e, []).form ?? "Something went wrong.");

  const usedCols: Column<InventoryUsage>[] = [
    { key: "when", header: "When", cell: (u) => <RelativeTime value={u.created_at} /> },
    { key: "who", header: "Who", cell: (u) => personName(u.used_by) },
    { key: "item", header: "Reagent", cell: (u) => u.item_name },
    { key: "amount", header: "Amount", cell: (u) => qty(u.amount, u.unit) },
    { key: "protocol", header: "Protocol", cell: (u) => u.protocol_name },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (u) =>
        u.reversed_at ? (
          <span className="text-xs text-muted-foreground">Undone</span>
        ) : u.can_reverse ? (
          <Button
            variant="ghost"
            size="sm"
            disabled={reverse.isPending}
            aria-label={`Undo ${u.item_name}`}
            onClick={() =>
              reverse.mutate(u.id, {
                onSuccess: () => toast.success("Put back in stock."),
                onError: fail,
              })
            }
          >
            Undo
          </Button>
        ) : null,
    },
  ];

  const protocols = list.data ?? [];
  return (
    <div className="grid gap-8">
      <section aria-label="Protocols" className="grid gap-3">
        {canEdit && protocols.length > 0 && (
          <div className="flex justify-end">
            <Button onClick={() => setEditing("new")}>Add protocol</Button>
          </div>
        )}
        {!list.isLoading && protocols.length === 0 && (
          <EmptyState
            icon={FlaskConical}
            title="No protocols yet"
            description="List the reagents and amounts a protocol uses. When you run it, record what you used and it comes off the lab's stock."
            action={
              canEdit ? <Button onClick={() => setEditing("new")}>Add protocol</Button> : undefined
            }
          />
        )}
        {protocols.map((p) => (
          <div key={p.id} className="grid gap-3 rounded-lg border p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <h3 className="font-semibold break-words">{p.name}</h3>
                {p.notes && <p className="text-sm text-muted-foreground">{p.notes}</p>}
              </div>
              {canEdit && (
                <div className="flex gap-1">
                  <Button variant="ghost" size="sm" onClick={() => setEditing(p)}>
                    Edit
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Delete ${p.name}`}
                    onClick={() =>
                      remove.mutate(p.id, {
                        onSuccess: () => toast.success("Protocol deleted"),
                        onError: fail,
                      })
                    }
                  >
                    Delete
                  </Button>
                </div>
              )}
            </div>
            <DataTable
              columns={[
                { key: "item", header: "Reagent", cell: (r: Reagent) => r.item_name },
                { key: "amount", header: "Amount", cell: (r: Reagent) => qty(r.amount, r.unit) },
                {
                  key: "stock",
                  header: "In stock",
                  cell: (r: Reagent) => qty(r.stock, r.stock_unit),
                },
                {
                  key: "actions",
                  header: "",
                  className: "text-right",
                  cell: (r: Reagent) =>
                    canEdit && (
                      <Button
                        size="sm"
                        variant="outline"
                        aria-label={`Used ${r.item_name}`}
                        onClick={() => setUsing({ protocol: p, reagent: r })}
                      >
                        Used this
                      </Button>
                    ),
                },
              ]}
              rows={p.reagents}
              getRowKey={(r) => r.id}
              loading={false}
              empty={
                <span className="text-sm text-muted-foreground">
                  No reagents listed yet. Edit this protocol to add them.
                </span>
              }
            />
          </div>
        ))}
      </section>

      <section aria-label="What was used" className="grid gap-3">
        <h3 className="text-sm font-semibold">What was used</h3>
        <DataTable
          columns={usedCols}
          rows={usage.data ?? []}
          getRowKey={(u) => u.id}
          loading={usage.isLoading}
          empty={<span className="text-sm text-muted-foreground">Nothing recorded yet.</span>}
        />
      </section>

      {editing && (
        <ProtocolDialog
          labId={labId}
          protocol={editing === "new" ? undefined : editing}
          save={save}
          onClose={() => setEditing(null)}
        />
      )}
      {using && (
        <UseDialog
          key={using.reagent.id}
          reagent={using.reagent}
          protocol={using.protocol}
          use={use}
          onClose={() => setUsing(null)}
        />
      )}
    </div>
  );
}

function UseDialog({
  protocol,
  reagent,
  use,
  onClose,
}: {
  protocol: Protocol;
  reagent: Reagent;
  use: ReturnType<typeof useProtocols>["use"];
  onClose: () => void;
}) {
  // One id per dialog: a double-click or a retried request takes stock only once (D228).
  const [requestId] = useState(() => crypto.randomUUID());
  const [error, setError] = useState<string>();

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    try {
      await use.mutateAsync({
        protocol: protocol.id,
        reagent: reagent.id,
        amount: str(new FormData(e.currentTarget), "amount"),
        request_id: requestId,
      });
      toast.success("Taken out of stock.");
      onClose();
    } catch (err) {
      const f = formErrors(err, ["amount", "reagent", "request_id"]);
      setError(Object.values(f.fields)[0] ?? f.form ?? "Something went wrong.");
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">
          Record use of {reagent.item_name}
        </DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          This takes it out of the lab&apos;s stock ({qty(reagent.stock, reagent.stock_unit)} now).
          You can undo it afterwards.
        </DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <FormField label={`Amount used (${reagent.unit || "no unit"})`} error={error}>
            {(p) => (
              <Input
                {...p}
                name="amount"
                inputMode="decimal"
                defaultValue={Number(reagent.amount)}
                autoFocus
              />
            )}
          </FormField>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={use.isPending}>
              Take out of stock
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ProtocolDialog({
  labId,
  protocol,
  save,
  onClose,
}: {
  labId: string;
  protocol?: Protocol;
  save: ReturnType<typeof useProtocols>["save"];
  onClose: () => void;
}) {
  const stock = useInventory(labId, {}).list.data ?? [];
  const [lines, setLines] = useState(
    protocol?.reagents.map((r) => ({ item: r.item, amount: r.amount })) ?? [
      { item: "", amount: "" },
    ],
  );
  const [error, setError] = useState<string>();
  const unitOf = (id: string) => stock.find((s) => s.id === id)?.unit ?? "";

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const name = str(f, "name");
    if (!name) return setError("Enter a name for the protocol.");
    const reagents = lines
      .filter((l) => l.item)
      .map((l) => ({ item: l.item, amount: l.amount, unit: unitOf(l.item) }));
    try {
      await save.mutateAsync({
        id: protocol?.id,
        body: { name, notes: str(f, "notes"), reagents },
      });
      toast.success("Protocol saved");
      onClose();
    } catch (err) {
      const fe = formErrors(err, ["name", "notes", "reagents"]);
      setError(Object.values(fe.fields)[0] ?? fe.form ?? "Something went wrong.");
    }
  }

  const change = (i: number, patch: Partial<(typeof lines)[number]>) =>
    setLines((ls) => ls.map((l, n) => (n === i ? { ...l, ...patch } : l)));

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle className="text-base font-semibold">
          {protocol ? "Edit protocol" : "Add protocol"}
        </DialogTitle>
        <DialogDescription className="sr-only">Protocol name and reagents</DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <FormField label="Name">
            {(p) => <Input {...p} name="name" defaultValue={protocol?.name} />}
          </FormField>
          <FormField label="Notes">
            {(p) => <Textarea {...p} name="notes" rows={2} defaultValue={protocol?.notes} />}
          </FormField>
          <div className="grid gap-2">
            <p className="text-sm font-medium">Reagents</p>
            {lines.map((line, i) => (
              <div key={i} className="grid grid-cols-[1fr_6rem_auto] items-end gap-2">
                <FormField label={`Reagent ${i + 1}`}>
                  {(p) => (
                    <NativeSelect
                      {...p}
                      value={line.item}
                      onChange={(e) => change(i, { item: e.target.value })}
                    >
                      <option value="">Pick an item</option>
                      {stock.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                </FormField>
                <FormField label={unitOf(line.item) || "Amount"}>
                  {(p) => (
                    <Input
                      {...p}
                      inputMode="decimal"
                      value={line.amount}
                      onChange={(e) => change(i, { amount: e.target.value })}
                    />
                  )}
                </FormField>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove reagent ${i + 1}`}
                  onClick={() => setLines((ls) => ls.filter((_, n) => n !== i))}
                >
                  Remove
                </Button>
              </div>
            ))}
            <div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setLines((ls) => [...ls, { item: "", amount: "" }])}
              >
                Add a reagent
              </Button>
            </div>
          </div>
          <FormError message={error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending}>
              Save
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
