import { useState, type FormEvent, type MouseEvent } from "react";
import { toast } from "sonner";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { inventoryExportUrl, useInventory } from "@/hooks/admin";
import { ImportInventory } from "./ImportInventory";
import { useMembers } from "@/hooks/workspace";
import type { InventoryInput, InventoryItem } from "@/lib/api-types";
import { localDateISO } from "@/lib/format";
import { formErrors, type FormErrors } from "@/lib/forms";
import { formValue, NativeSelect, Section } from "./common";

export const CATEGORIES = [
  { value: "equipment", label: "Equipment" },
  { value: "reagent", label: "Reagent" },
  { value: "consumable", label: "Consumable" },
  { value: "software_licence", label: "Software licence" },
  { value: "other", label: "Other" },
] as const;
export const STATUSES = [
  { value: "active", label: "Active" },
  { value: "in_repair", label: "In repair" },
  { value: "retired", label: "Retired" },
  { value: "lost", label: "Lost" },
] as const;
const nameOf = (list: readonly { value: string; label: string }[], v: string) =>
  list.find((x) => x.value === v)?.label ?? v;

const SORTS = [
  { value: "name", label: "Name" },
  { value: "category", label: "Category" },
  { value: "due_date", label: "Due date" },
  { value: "status", label: "Status" },
  { value: "location", label: "Location" },
];
const KNOWN = [
  "name",
  "category",
  "location",
  "quantity",
  "unit",
  "owner",
  "serial_number",
  "purchase_date",
  "due_date",
  "status",
  "notes",
];

const PICK_TODAY_HINT = "Double-click to pick today";
const pickToday = (e: MouseEvent<HTMLInputElement>) => {
  e.currentTarget.value = localDateISO();
};

function ItemDialog({
  labId,
  item,
  open,
  onClose,
  create,
  update,
}: {
  labId: string;
  item: InventoryItem | null;
  open: boolean;
  onClose: () => void;
  create: ReturnType<typeof useInventory>["create"];
  update: ReturnType<typeof useInventory>["update"];
}) {
  const members = useMembers(labId).data ?? [];
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const v = (k: string) => formValue(fd, k);
    if (!v("name")) return setErrors({ fields: { name: "Enter a name" } });
    const body = {
      name: v("name"),
      category: v("category") as InventoryInput["category"],
      location: v("location"),
      quantity: v("quantity") || "1",
      unit: v("unit"),
      owner: v("owner") || null,
      serial_number: v("serial_number"),
      purchase_date: v("purchase_date") || null,
      due_date: v("due_date") || null,
      status: v("status") as InventoryInput["status"],
      notes: v("notes"),
    };
    try {
      if (item) {
        // Stock moves while this form is open: only a number someone typed may replace it (D244).
        const { quantity, ...rest } = body;
        const typed = Number(quantity) !== Number(item.quantity);
        await update.mutateAsync({ id: item.id, ...rest, ...(typed && { quantity }) });
      } else await create.mutateAsync(body);
      setErrors({ fields: {} });
      toast.success(item ? "Item saved" : "Item added");
      onClose();
    } catch (err) {
      setErrors(formErrors(err, KNOWN));
    }
  }

  const f = errors.fields;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle className="text-base font-semibold">
          {item ? "Edit item" : "Add an item"}
        </DialogTitle>
        <DialogDescription className="sr-only">Inventory item details</DialogDescription>
        <form key={item?.id ?? "new"} onSubmit={submit} noValidate className="grid gap-3">
          <FormField label="Name" error={f.name}>
            {(p) => <Input maxLength={200} {...p} name="name" defaultValue={item?.name} />}
          </FormField>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Category" error={f.category}>
              {(p) => (
                <NativeSelect {...p} name="category" defaultValue={item?.category ?? "equipment"}>
                  {CATEGORIES.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <FormField label="Status" error={f.status}>
              {(p) => (
                <NativeSelect {...p} name="status" defaultValue={item?.status ?? "active"}>
                  {STATUSES.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <FormField label="Quantity" error={f.quantity}>
              {(p) => (
                <Input
                  {...p}
                  name="quantity"
                  type="number"
                  min="0"
                  step="any"
                  defaultValue={item?.quantity ?? "1"}
                />
              )}
            </FormField>
            <FormField label="Unit" error={f.unit}>
              {(p) => <Input maxLength={32} {...p} name="unit" defaultValue={item?.unit} />}
            </FormField>
            <FormField label="Location" error={f.location}>
              {(p) => (
                <Input maxLength={200} {...p} name="location" defaultValue={item?.location} />
              )}
            </FormField>
            <FormField label="Owner" error={f.owner}>
              {(p) => (
                <NativeSelect {...p} name="owner" defaultValue={item?.owner?.id ?? ""}>
                  <option value="">No owner</option>
                  {members.map((m) => (
                    <option key={m.id} value={m.user.id}>
                      {m.user.display_name || m.user.email}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <FormField label="Serial or asset number" error={f.serial_number}>
              {(p) => (
                <Input
                  maxLength={100}
                  {...p}
                  name="serial_number"
                  defaultValue={item?.serial_number}
                />
              )}
            </FormField>
            <FormField label="Purchase date" error={f.purchase_date}>
              {(p) => (
                <Input
                  {...p}
                  name="purchase_date"
                  type="date"
                  title={PICK_TODAY_HINT}
                  onDoubleClick={pickToday}
                  defaultValue={item?.purchase_date ?? ""}
                />
              )}
            </FormField>
            <FormField label="Calibration or maintenance due" error={f.due_date}>
              {(p) => (
                <Input
                  {...p}
                  name="due_date"
                  type="date"
                  title={PICK_TODAY_HINT}
                  onDoubleClick={pickToday}
                  defaultValue={item?.due_date ?? ""}
                />
              )}
            </FormField>
          </div>
          <FormField label="Notes" error={f.notes}>
            {(p) => (
              <Textarea maxLength={5000} {...p} name="notes" rows={3} defaultValue={item?.notes} />
            )}
          </FormField>
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit">Save</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function InventorySection({
  labId,
  canEdit,
  onReorder,
}: {
  labId: string;
  canEdit: boolean;
  /** The Inventory page passes this to show a Reorder action; Admin leaves it out. */
  onReorder?: (item: InventoryItem) => void;
}) {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [ordering, setOrdering] = useState("name");
  const query = { q, category, ordering };
  const { list, remove, create, update } = useInventory(labId, query);
  const [editing, setEditing] = useState<InventoryItem | null>(null);
  const [adding, setAdding] = useState(false);

  const cols: Column<InventoryItem>[] = [
    { key: "name", header: "Name", cell: (i) => <span className="font-medium">{i.name}</span> },
    { key: "category", header: "Category", cell: (i) => nameOf(CATEGORIES, i.category) },
    { key: "location", header: "Location", cell: (i) => i.location || "-" },
    { key: "qty", header: "Quantity", cell: (i) => `${Number(i.quantity)} ${i.unit}`.trim() },
    {
      key: "owner",
      header: "Owner",
      cell: (i) => (i.owner ? i.owner.display_name || i.owner.email : "-"),
    },
    { key: "due", header: "Due", cell: (i) => i.due_date ?? "-" },
    { key: "status", header: "Status", cell: (i) => nameOf(STATUSES, i.status) },
    ...(canEdit
      ? [
          {
            key: "actions",
            header: "Actions",
            className: "text-right",
            cell: (i: InventoryItem) => (
              <div className="flex justify-end gap-1">
                {onReorder && (
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Reorder ${i.name}`}
                    onClick={() => onReorder(i)}
                  >
                    Reorder
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Edit ${i.name}`}
                  onClick={() => setEditing(i)}
                >
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Delete ${i.name}`}
                  onClick={() =>
                    remove.mutate(i.id, {
                      onSuccess: () => toast.success("Item deleted"),
                      onError: (e) =>
                        toast.error(formErrors(e, []).form ?? "Could not delete the item."),
                    })
                  }
                >
                  Delete
                </Button>
              </div>
            ),
          },
        ]
      : []),
  ];

  return (
    <Section
      title="Inventory"
      description={
        canEdit ? "Equipment, reagents and licences the lab owns." : "Read only for your role."
      }
    >
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-56">
          <FormField label="Search">
            {(p) => <Input {...p} type="search" value={q} onChange={(e) => setQ(e.target.value)} />}
          </FormField>
        </div>
        <div className="w-44">
          <FormField label="Filter by category">
            {(p) => (
              <NativeSelect {...p} value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">All categories</option>
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
        </div>
        <div className="w-44">
          <FormField label="Sort by">
            {(p) => (
              <NativeSelect {...p} value={ordering} onChange={(e) => setOrdering(e.target.value)}>
                {SORTS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
        </div>
        <Button variant="outline" asChild>
          <a href={inventoryExportUrl(labId, query)} download="inventory.csv">
            Export CSV
          </a>
        </Button>
        {canEdit && <ImportInventory labId={labId} />}
        {canEdit && <Button onClick={() => setAdding(true)}>Add item</Button>}
      </div>
      <DataTable
        columns={cols}
        rows={list.data ?? []}
        getRowKey={(i) => i.id}
        loading={list.isLoading}
        empty={
          <EmptyState title="No inventory items" description="Items you add will appear here." />
        }
      />
      <ItemDialog
        labId={labId}
        create={create}
        update={update}
        item={editing}
        open={adding || !!editing}
        onClose={() => {
          setAdding(false);
          setEditing(null);
        }}
      />
    </Section>
  );
}
