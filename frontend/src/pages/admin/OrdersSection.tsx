import { useState, type FormEvent } from "react";
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
import { ordersExportUrl, useOrders } from "@/hooks/admin";
import {
  personName,
  type InventoryItem,
  type InventoryOrder,
  type OrderStatus,
} from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { vendorLinks } from "@/lib/vendors";
import { formValue, NativeSelect, Section } from "./common";

const STATUSES: { value: OrderStatus; label: string }[] = [
  { value: "requested", label: "Requested" },
  { value: "ordered", label: "Ordered" },
  { value: "received", label: "Received" },
  { value: "cancelled", label: "Cancelled" },
];
const KNOWN = ["item", "name", "vendor", "catalog_number", "url", "quantity", "unit", "notes"];
const qty = (o: InventoryOrder) => `${Number(o.quantity)} ${o.unit}`.trim();

type Orders = ReturnType<typeof useOrders>;

function OrderDialog({
  reorder,
  last,
  open,
  onClose,
  create,
}: {
  reorder: InventoryItem | null;
  /** The newest order for the item being reordered: its vendor details are reused. */
  last: InventoryOrder | undefined;
  open: boolean;
  onClose: () => void;
  create: Orders["create"];
}) {
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [name, setName] = useState(reorder?.name ?? "");
  const [catalog, setCatalog] = useState(last?.catalog_number ?? "");
  const term = (catalog || name).trim();

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const v = (k: string) => formValue(fd, k);
    if (!name.trim()) return setErrors({ fields: { name: "Enter a name" } });
    try {
      await create.mutateAsync({
        item: reorder?.id ?? null,
        name: name.trim(),
        vendor: v("vendor"),
        catalog_number: catalog.trim(),
        url: v("url"),
        quantity: v("quantity") || "1",
        unit: v("unit"),
        notes: v("notes"),
      });
      toast.success("Order added");
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
          {reorder ? `Reorder ${reorder.name}` : "New order"}
        </DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          {reorder
            ? "When this order is marked received, its quantity is added to the item."
            : "Request something for the lab."}
        </DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <FormField label="Name" error={f.name}>
            {(p) => <Input {...p} value={name} onChange={(e) => setName(e.target.value)} />}
          </FormField>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Vendor" error={f.vendor}>
              {(p) => <Input {...p} name="vendor" defaultValue={last?.vendor} />}
            </FormField>
            <FormField label="Catalog number" error={f.catalog_number}>
              {(p) => <Input {...p} value={catalog} onChange={(e) => setCatalog(e.target.value)} />}
            </FormField>
            <FormField label="Quantity" error={f.quantity}>
              {(p) => (
                <Input
                  {...p}
                  name="quantity"
                  type="number"
                  min="0.01"
                  step="any"
                  defaultValue={last ? Number(last.quantity) : 1}
                />
              )}
            </FormField>
            <FormField label="Unit" error={f.unit}>
              {(p) => <Input {...p} name="unit" defaultValue={last?.unit ?? reorder?.unit} />}
            </FormField>
          </div>
          <FormField label="Order link" hint="Must start with https://" error={f.url}>
            {(p) => <Input {...p} name="url" type="url" defaultValue={last?.url} />}
          </FormField>
          <div className="grid gap-1">
            <p className="text-xs text-muted-foreground">
              {term
                ? `Search vendors for "${term}":`
                : "Enter a name or catalog number to search vendors."}
            </p>
            {term && (
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-sm">
                {vendorLinks(term).map((v) => (
                  <a
                    key={v.name}
                    href={v.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline underline-offset-2"
                  >
                    {v.name}
                  </a>
                ))}
              </div>
            )}
          </div>
          <FormField label="Notes" error={f.notes}>
            {(p) => <Textarea {...p} name="notes" rows={2} />}
          </FormField>
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={create.isPending}>
              Save
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function OrdersSection({
  labId,
  canEdit,
  reorder,
  onReorderClose,
}: {
  labId: string;
  canEdit: boolean;
  reorder: InventoryItem | null;
  onReorderClose: () => void;
}) {
  const { list, create, update, refreshStock } = useOrders(labId);
  const [adding, setAdding] = useState(false);
  const [receiving, setReceiving] = useState<InventoryOrder>();
  const orders = list.data ?? [];

  function setStatus(order: InventoryOrder, status: OrderStatus) {
    update.mutate(
      { id: order.id, status },
      {
        onSuccess: () => {
          toast.success("Order updated");
          if (status === "received") void refreshStock();
        },
        onError: (e) => toast.error(formErrors(e, []).form ?? "Could not update the order."),
        onSettled: () => setReceiving(undefined),
      },
    );
  }

  const cols: Column<InventoryOrder>[] = [
    {
      key: "name",
      header: "Name",
      cell: (o) => (
        <div className="min-w-32">
          <span className="font-medium">{o.name}</span>
          <p className="text-xs text-muted-foreground">
            {[o.vendor, o.catalog_number].filter(Boolean).join(" · ") || o.item_name}
          </p>
        </div>
      ),
    },
    { key: "qty", header: "Quantity", cell: qty },
    {
      key: "status",
      header: "Status",
      cell: (o) =>
        canEdit && o.status !== "received" ? (
          <NativeSelect
            aria-label={`Status of ${o.name}`}
            value={o.status}
            className="w-32"
            onChange={(e) => {
              const next = e.target.value as OrderStatus;
              if (next === "received") setReceiving(o);
              else setStatus(o, next);
            }}
          >
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </NativeSelect>
        ) : (
          (STATUSES.find((s) => s.value === o.status)?.label ?? o.status)
        ),
    },
    { key: "by", header: "Requested by", cell: (o) => personName(o.requested_by) },
    {
      key: "actions",
      header: "Actions",
      className: "text-right",
      cell: (o) =>
        o.url ? (
          <Button variant="outline" size="sm" asChild>
            <a href={o.url} target="_blank" rel="noopener noreferrer">
              Place order<span className="sr-only">: {o.name}</span>
            </a>
          </Button>
        ) : (
          "-"
        ),
    },
  ];

  const last = reorder ? orders.find((o) => o.item === reorder.id) : undefined;
  return (
    <Section title="Orders" description="What the lab has asked for and what has arrived.">
      <div className="flex flex-wrap gap-3">
        <Button variant="outline" asChild>
          <a href={ordersExportUrl(labId)} download="orders.csv">
            Export orders CSV
          </a>
        </Button>
        {canEdit && <Button onClick={() => setAdding(true)}>New order</Button>}
      </div>
      <DataTable
        columns={cols}
        rows={orders}
        getRowKey={(o) => o.id}
        loading={list.isLoading}
        empty={<EmptyState title="No orders" description="Orders you add will appear here." />}
      />
      <OrderDialog
        key={reorder?.id ?? String(adding)}
        reorder={reorder}
        last={last}
        open={adding || !!reorder}
        create={create}
        onClose={() => {
          setAdding(false);
          onReorderClose();
        }}
      />
      <Dialog open={!!receiving} onOpenChange={(o) => !o && setReceiving(undefined)}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Mark as received?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            {receiving?.item
              ? `This adds ${receiving ? qty(receiving) : ""} to ${receiving?.item_name}. It cannot be undone here.`
              : "This cannot be undone here."}
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button
              disabled={update.isPending}
              onClick={() => receiving && setStatus(receiving, "received")}
            >
              Mark received
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Section>
  );
}
