import { MoreMenu } from "@/components/shared/MoreMenu";
import { useState, type FormEvent, type MouseEvent } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { DataTable, HIDE_NARROW, HIDE_NARROWER, type Column } from "@/components/shared/DataTable";
import { BulkBar, SelectBox, reportBulk, runEach, useSelection } from "@/components/shared/bulk";
import { ConfirmDelete } from "@/components/shared/ConfirmDelete";
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
import { inventoryExportUrl, useInventory, useOrders } from "@/hooks/admin";
import { useIsPhone } from "@/hooks/media";
import { ImportInventory } from "./ImportInventory";
import { UseStockDialog } from "./UseStockDialog";
import { Minus, Search, TriangleAlert } from "lucide-react";
import { trimNumber } from "@/lib/units";
import { useMembers } from "@/hooks/workspace";
import type { InventoryInput, InventoryItem, InventoryOrder } from "@/lib/api-types";
import { localDateISO } from "@/lib/format";
import { formErrors, type FormErrors } from "@/lib/forms";
import { saveBlob } from "@/lib/exportFiles";
import { formValue, NativeSelect, Section } from "./common";

const csvCell = (v: unknown) => {
  const t = v == null ? "" : String(v);
  const safe = /^[=+\-@\t\r]/.test(t) ? `'${t}` : t; // a leading = + - @ makes Excel run the cell
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
};
function exportRows(items: InventoryItem[]) {
  const head = ["Name", "Category", "Location", "Quantity", "Unit", "Owner", "Serial number"];
  head.push("Purchase date", "Due date", "Status", "Notes");
  const lines = items.map((i) =>
    [i.name, i.category, i.location, i.quantity, i.unit, i.owner?.display_name || i.owner?.email]
      .concat([i.serial_number, i.purchase_date, i.due_date, i.status, i.notes] as string[])
      .map(csvCell)
      .join(","),
  );
  saveBlob(
    new Blob([[head.join(","), ...lines].join("\r\n")], { type: "text/csv;charset=utf-8" }),
    "inventory-selected.csv",
  );
}

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
  "low_stock_at",
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
      low_stock_at: v("low_stock_at") || null,
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
            <FormField
              label="Alert me at or below"
              hint="Leave empty for no alert. The PIs, admins and the owner are told when stock falls to this."
              error={f.low_stock_at}
            >
              {(p) => (
                <Input
                  {...p}
                  name="low_stock_at"
                  type="number"
                  min="0"
                  step="any"
                  defaultValue={item?.low_stock_at ? trimNumber(item.low_stock_at) : ""}
                />
              )}
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

/** "about 3 weeks left", from the server's rate over the last 8 weeks; nothing without one. */
function WeeksLeft({ item: i }: { item: InventoryItem }) {
  if (i.weeks_left == null || i.status === "retired") return null;
  const text =
    i.weeks_left < 1
      ? "less than a week left"
      : `about ${i.weeks_left} ${i.weeks_left === 1 ? "week" : "weeks"} left`;
  return (
    <span className="text-xs text-muted-foreground" title="Based on uses in the last 8 weeks">
      {text}
    </span>
  );
}

/** Open orders (requested or ordered) for the item: they have not arrived, so they are not stock. */
function OnOrder({ orders }: { orders: InventoryOrder[] }) {
  if (orders.length === 0) return null;
  const units = new Set(orders.map((o) => o.unit));
  const total = orders.reduce((n, o) => n + Number(o.quantity), 0);
  const text =
    units.size === 1
      ? `${trimNumber(total)} ${orders[0]?.unit}`.trim() + " on order"
      : `${orders.length} orders on the way`;
  return <span className="text-xs text-muted-foreground">{text}</span>;
}

function LowBadge({ item: i }: { item: InventoryItem }) {
  return (
    <span
      title={`At or below the alert level of ${trimNumber(i.low_stock_at ?? 0)} ${i.unit}`}
      className="inline-flex items-center gap-1 rounded-full bg-warning/25 px-2 py-0.5 text-xs font-semibold text-warning-text"
    >
      <TriangleAlert aria-hidden className="size-3" /> Low
    </span>
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
  const [lowOnly, setLowOnly] = useState(false);
  const query = { q, category, ordering };
  const { list, remove, create, update } = useInventory(labId, query);
  const rows = (list.data ?? []).filter((i) => !lowOnly || i.low);
  const phone = useIsPhone();
  const [editing, setEditing] = useState<InventoryItem | null>(null);
  const [adding, setAdding] = useState(false);
  // the command palette's "Add inventory item" lands here with ?add=1
  const [params, setParams] = useSearchParams();
  const addFromLink = canEdit && params.get("add") === "1";
  const clearAdd = () =>
    setParams(
      (p) => {
        p.delete("add");
        return p;
      },
      { replace: true },
    );
  const selection = useSelection(rows.map((i) => i.id));
  const [selecting, setSelecting] = useState(false); // phones: the cards get checkboxes
  const [bulk, setBulk] = useState<"alert" | "delete" | null>(null);
  const picked = rows.filter((i) => selection.has(i.id));
  const bulkEach = async (past: string, run: (i: InventoryItem) => Promise<unknown>) => {
    reportBulk(past, "item", picked.length, await runEach(picked, run, (i) => i.name));
    selection.clear();
    setBulk(null);
  };
  const [deleting, setDeleting] = useState<InventoryItem | null>(null);
  const orders = useOrders(labId).list.data ?? [];
  const openOrders = (i: InventoryItem) =>
    orders.filter((o) => o.item === i.id && (o.status === "requested" || o.status === "ordered"));
  const [usingId, setUsing] = useState<string | null>(null);
  const using = (list.data ?? []).find((i) => i.id === usingId) ?? null;

  const actions = (i: InventoryItem) => (
    <div className="flex justify-end gap-1">
      {i.status !== "retired" &&
        i.category !== "equipment" &&
        i.category !== "software_licence" && (
          <Button
            variant="outline"
            size="sm"
            aria-label={`Use ${i.name}`}
            title="Log what you used; it comes off the stock"
            onClick={() => setUsing(i.id)}
          >
            <Minus aria-hidden /> Use
          </Button>
        )}
      {onReorder && i.low && i.status !== "retired" && (
        <Button
          variant="outline"
          size="sm"
          aria-label={`Reorder ${i.name}`}
          onClick={() => onReorder(i)}
        >
          Reorder
        </Button>
      )}
      <MoreMenu
        label={`More for ${i.name}`}
        items={[
          onReorder && { label: "Reorder", onSelect: () => onReorder(i) },
          { label: "Edit", onSelect: () => setEditing(i) },
          {
            label: "Delete",
            onSelect: () => setDeleting(i),
          },
        ]}
      />
    </div>
  );

  const cols: Column<InventoryItem>[] = [
    { key: "name", header: "Name", cell: (i) => <span className="font-medium">{i.name}</span> },
    {
      key: "category",
      header: "Category",
      className: HIDE_NARROW,
      cell: (i) => nameOf(CATEGORIES, i.category),
    },
    {
      key: "location",
      header: "Location",
      className: HIDE_NARROWER,
      cell: (i) => i.location || "-",
    },
    {
      key: "qty",
      header: "Quantity",
      cell: (i) => (
        <span className="inline-flex items-center gap-2">
          {`${trimNumber(i.quantity)} ${i.unit}`.trim()}
          {i.low && i.status !== "retired" && <LowBadge item={i} />}
          <WeeksLeft item={i} />
          <OnOrder orders={openOrders(i)} />
        </span>
      ),
    },
    {
      key: "owner",
      header: "Owner",
      className: HIDE_NARROWER,
      cell: (i) => (i.owner ? i.owner.display_name || i.owner.email : "-"),
    },
    { key: "due", header: "Due", className: HIDE_NARROW, cell: (i) => i.due_date ?? "-" },
    { key: "status", header: "Status", cell: (i) => nameOf(STATUSES, i.status) },
    ...(canEdit
      ? [
          {
            key: "actions",
            header: "Actions",
            className: "text-right whitespace-nowrap",
            cell: actions,
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
      <div className="grid gap-3 sm:flex sm:flex-wrap sm:items-end">
        <div className="sm:w-56">
          <FormField label="Search">
            {(p) => (
              <div className="relative">
                <Search
                  aria-hidden
                  className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                />
                <Input
                  {...p}
                  type="search"
                  placeholder="Search items"
                  className="pl-9"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </div>
            )}
          </FormField>
        </div>
        <div className="sm:w-44">
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
        <div className="sm:w-44">
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
        <label className="flex h-9 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={lowOnly}
            onChange={(e) => setLowOnly(e.target.checked)}
            className="size-4 accent-primary"
          />
          Low stock only
        </label>
        <div className="flex flex-wrap gap-2 sm:ml-auto">
          <Button variant="outline" asChild>
            <a href={inventoryExportUrl(labId, query)} download="inventory.csv">
              Export CSV
            </a>
          </Button>
          {canEdit && <ImportInventory labId={labId} />}
          {canEdit && !onReorder && <Button onClick={() => setAdding(true)}>Add item</Button>}
        </div>
      </div>
      {phone && rows.length > 0 && (
        <Button
          variant="outline"
          className="justify-self-start"
          aria-pressed={selecting}
          onClick={() => {
            setSelecting(!selecting);
            selection.clear();
          }}
        >
          {selecting ? "Done selecting" : "Select"}
        </Button>
      )}
      <BulkBar selection={selection}>
        {canEdit && (
          <>
            <Button variant="outline" size="sm" onClick={() => setBulk("alert")}>
              Set alert level
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                void bulkEach("Retired", (i) => update.mutateAsync({ id: i.id, status: "retired" }))
              }
            >
              Retire
            </Button>
            <Button variant="outline" size="sm" onClick={() => setBulk("delete")}>
              Delete
            </Button>
          </>
        )}
        <Button variant="outline" size="sm" onClick={() => exportRows(picked)}>
          Export selected
        </Button>
      </BulkBar>
      {phone && !list.isLoading && rows.length > 0 ? (
        <ul className="grid gap-2" aria-label="Inventory items">
          {rows.map((i) => (
            <li key={i.id} className="grid gap-2 rounded-lg border p-3">
              <div className="flex items-start justify-between gap-2">
                {selecting && (
                  <SelectBox
                    checked={selection.has(i.id)}
                    label={`Select ${i.name}`}
                    onToggle={(shift) => selection.toggle(i.id, shift)}
                  />
                )}
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{i.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {[nameOf(CATEGORIES, i.category), i.location].filter(Boolean).join(" · ")}
                  </p>
                </div>
                <span className="flex shrink-0 items-center gap-2 text-sm">
                  {`${trimNumber(i.quantity)} ${i.unit}`.trim()}
                  {i.low && i.status !== "retired" && <LowBadge item={i} />}
                  <WeeksLeft item={i} />
                  <OnOrder orders={openOrders(i)} />
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {[
                  nameOf(STATUSES, i.status),
                  i.owner && (i.owner.display_name || i.owner.email),
                  i.due_date && `Due ${i.due_date}`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              {canEdit && actions(i)}
            </li>
          ))}
        </ul>
      ) : (
        <DataTable
          columns={cols}
          rows={rows}
          getRowKey={(i) => i.id}
          selection={selection}
          selectLabel={(i) => `Select ${i.name}`}
          loading={list.isLoading}
          empty={
            <EmptyState
              compact
              title={lowOnly ? "Nothing is low" : "No inventory items"}
              description={
                lowOnly
                  ? "No item is at or below its alert level."
                  : canEdit
                    ? "Items you add will appear here."
                    : "Only people who manage inventory can add items. Ask a PI or lab admin."
              }
              action={
                canEdit && !lowOnly ? (
                  <Button onClick={() => setAdding(true)}>Add item</Button>
                ) : undefined
              }
            />
          }
        />
      )}
      <ConfirmDelete
        open={!!deleting}
        name={deleting?.name ?? ""}
        noun="item"
        description="Items still used by a protocol or a record of use can't be deleted. Mark them retired instead."
        pending={remove.isPending}
        onClose={() => setDeleting(null)}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.id, {
            onSuccess: () => toast.success("Item deleted"),
            onError: (e) => toast.error(formErrors(e, []).form ?? "Could not delete the item."),
            onSettled: () => setDeleting(null),
          })
        }
      />
      <ConfirmDelete
        open={bulk === "delete"}
        name={`${picked.length} ${picked.length === 1 ? "item" : "items"}`}
        noun={picked.length === 1 ? "item" : "items"}
        items={picked.map((i) => i.name)}
        description="Items still used by a protocol or a record of use can't be deleted; they stay, and you'll see which. Mark them retired instead."
        onConfirm={() => void bulkEach("Deleted", (i) => remove.mutateAsync(i.id))}
        onClose={() => setBulk(null)}
      />
      <Dialog open={bulk === "alert"} onOpenChange={(o) => !o && setBulk(null)}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">
            Set alert level for {picked.length} {picked.length === 1 ? "item" : "items"}
          </DialogTitle>
          <DialogDescription className="sr-only">Low stock alert level</DialogDescription>
          <form
            noValidate
            className="grid gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              const v = formValue(new FormData(e.currentTarget), "level");
              void bulkEach("Updated", (i) =>
                update.mutateAsync({ id: i.id, low_stock_at: v || null }),
              );
            }}
          >
            <FormField
              label="Alert me at or below"
              hint="Leave empty to turn the alert off for these items."
            >
              {(p) => <Input {...p} name="level" type="number" min="0" step="any" />}
            </FormField>
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
      {using && <UseStockDialog labId={labId} item={using} onClose={() => setUsing(null)} />}
      <ItemDialog
        labId={labId}
        create={create}
        update={update}
        item={editing}
        open={adding || addFromLink || !!editing}
        onClose={() => {
          setAdding(false);
          setEditing(null);
          if (addFromLink) clearAdd();
        }}
      />
    </Section>
  );
}
