import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ConfirmDelete } from "@/components/shared/ConfirmDelete";
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
import { useIsPhone } from "@/hooks/media";
import { ordersExportUrl, useOrders } from "@/hooks/admin";
import {
  personName,
  type InventoryItem,
  type InventoryOrder,
  type OrderStatus,
} from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { vendorLinks } from "@/lib/vendors";
import { formValue, Section } from "./common";

const STATUSES: { value: OrderStatus; label: string }[] = [
  { value: "requested", label: "Requested" },
  { value: "ordered", label: "Ordered" },
  { value: "received", label: "Received" },
  { value: "cancelled", label: "Cancelled" },
];
const KNOWN = ["item", "name", "vendor", "catalog_number", "url", "quantity", "unit", "notes"];
const qty = (o: InventoryOrder) => `${Number(o.quantity)} ${o.unit}`.trim();

type Orders = ReturnType<typeof useOrders>;

/** Enough to get back to twice the alert level; with no alert level, what was ordered last time. */
export function suggestedQuantity(item: InventoryItem | null, last: InventoryOrder | undefined) {
  if (item?.low_stock_at != null)
    return Math.max(
      1,
      Math.round((Number(item.low_stock_at) * 2 - Number(item.quantity)) * 1e6) / 1e6,
    );
  return last ? Number(last.quantity) : 1;
}

function OrderDialog({
  reorder,
  last,
  pending,
  open,
  onClose,
  create,
}: {
  reorder: InventoryItem | null;
  /** The newest order for the item being reordered: its vendor details are reused. */
  last: InventoryOrder | undefined;
  /** Open orders (requested or ordered) for this item: a warning, never a block. */
  pending: InventoryOrder[];
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
        {pending.length > 0 && (
          <p role="note" className="rounded-md bg-warning/25 px-3 py-2 text-sm text-warning-text">
            Already on order:{" "}
            {pending
              .map(
                (o) =>
                  `${qty(o)}, ${o.status} ${new Date(o.created_at).toLocaleDateString("en-CA", { day: "numeric", month: "short" })}`,
              )
              .join("; ")}
            . You can still order more.
          </p>
        )}
        <form onSubmit={submit} noValidate className="grid gap-3">
          <FormField label="Name" error={f.name}>
            {(p) => (
              <Input
                maxLength={200}
                {...p}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            )}
          </FormField>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label="Vendor" error={f.vendor}>
              {(p) => <Input maxLength={200} {...p} name="vendor" defaultValue={last?.vendor} />}
            </FormField>
            <FormField label="Catalog number" error={f.catalog_number}>
              {(p) => (
                <Input
                  maxLength={100}
                  {...p}
                  value={catalog}
                  onChange={(e) => setCatalog(e.target.value)}
                />
              )}
            </FormField>
            <FormField label="Quantity" error={f.quantity}>
              {(p) => (
                <Input
                  {...p}
                  name="quantity"
                  type="number"
                  min="0.01"
                  step="any"
                  defaultValue={suggestedQuantity(reorder, last)}
                />
              )}
            </FormField>
            <FormField label="Unit" error={f.unit}>
              {(p) => (
                <Input
                  maxLength={32}
                  {...p}
                  name="unit"
                  defaultValue={last?.unit ?? reorder?.unit}
                />
              )}
            </FormField>
          </div>
          <FormField label="Order link" hint="Must start with https://" error={f.url}>
            {(p) => <Input maxLength={500} {...p} name="url" type="url" defaultValue={last?.url} />}
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
            {(p) => <Textarea maxLength={5000} {...p} name="notes" rows={2} />}
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
  const { list, create, update, remove, refreshStock } = useOrders(labId);
  const [adding, setAdding] = useState(false);
  const [receiving, setReceiving] = useState<InventoryOrder>();
  const [cancelling, setCancelling] = useState<InventoryOrder>();
  const [deleting, setDeleting] = useState<InventoryOrder>();
  const orders = list.data ?? [];
  const phone = useIsPhone();

  function setStatus(order: InventoryOrder, status: OrderStatus) {
    const wasReceived = order.status === "received";
    update.mutate(
      { id: order.id, status },
      {
        onSuccess: () => {
          toast.success(
            status === "cancelled"
              ? order.status === "requested"
                ? "Request declined"
                : "Order cancelled"
              : status === "ordered"
                ? "Marked as ordered. Place it with the vendor if you haven't; labbenchos doesn't contact vendors."
                : "Order updated",
          );
          if (status === "received" || wasReceived) void refreshStock();
        },
        onError: (e) => toast.error(formErrors(e, []).form ?? "Could not update the order."),
        onSettled: () => {
          setReceiving(undefined);
          setCancelling(undefined);
        },
      },
    );
  }

  const statusCell = (o: InventoryOrder) =>
    STATUSES.find((s) => s.value === o.status)?.label ?? o.status;

  const actionsCell = (o: InventoryOrder) => (
    <div className="flex flex-wrap justify-end gap-2">
      {o.url && (o.status === "requested" || o.status === "ordered") && (
        <Button variant="outline" size="sm" asChild>
          <a href={o.url} target="_blank" rel="noopener noreferrer">
            Open vendor page<span className="sr-only">: {o.name}</span>
          </a>
        </Button>
      )}
      {canEdit && o.status === "requested" && (
        <>
          <Button size="sm" disabled={update.isPending} onClick={() => setStatus(o, "ordered")}>
            Approve and mark ordered<span className="sr-only">: {o.name}</span>
          </Button>
          <Button variant="outline" size="sm" onClick={() => setStatus(o, "cancelled")}>
            Decline<span className="sr-only">: {o.name}</span>
          </Button>
        </>
      )}
      {canEdit && o.status === "ordered" && (
        <>
          <Button size="sm" onClick={() => setReceiving(o)}>
            Mark received<span className="sr-only">: {o.name}</span>
          </Button>
          <Button variant="outline" size="sm" onClick={() => setStatus(o, "cancelled")}>
            Cancel order<span className="sr-only">: {o.name}</span>
          </Button>
        </>
      )}
      {canEdit && o.status === "received" && (
        <Button variant="outline" size="sm" onClick={() => setCancelling(o)}>
          Undo receipt<span className="sr-only">: {o.name}</span>
        </Button>
      )}
      {canEdit && o.status === "cancelled" && (
        <Button variant="outline" size="sm" onClick={() => setDeleting(o)}>
          Delete<span className="sr-only">: {o.name}</span>
        </Button>
      )}
    </div>
  );

  const cols: Column<InventoryOrder>[] = [
    {
      key: "name",
      header: "Name",
      cell: (o) => (
        <div className="min-w-32">
          <span className="font-medium">{o.name}</span>
          <p className="text-xs text-muted-foreground">
            {[o.vendor, o.catalog_number].filter(Boolean).join(" · ") ||
              (o.item_name !== o.name ? o.item_name : "")}
          </p>
        </div>
      ),
    },
    { key: "qty", header: "Quantity", cell: qty },
    {
      key: "status",
      header: "Status",
      cell: statusCell,
    },
    { key: "by", header: "Requested by", cell: (o) => personName(o.requested_by) },
    {
      key: "actions",
      header: "Actions",
      className: "text-right",
      cell: actionsCell,
    },
  ];

  const open = reorder
    ? orders.filter(
        (o) => o.item === reorder.id && (o.status === "requested" || o.status === "ordered"),
      )
    : [];
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
      {phone && !list.isLoading && orders.length > 0 ? (
        <ul className="grid gap-2" aria-label="Orders">
          {orders.map((o) => (
            <li key={o.id} className="grid gap-2 rounded-lg border p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{o.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {[o.vendor, o.catalog_number].filter(Boolean).join(" · ") ||
                      (o.item_name !== o.name ? o.item_name : "")}
                  </p>
                </div>
                <span className="shrink-0 text-sm">{qty(o)}</span>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                {statusCell(o)}
                <span className="text-xs text-muted-foreground">{personName(o.requested_by)}</span>
              </div>
              {actionsCell(o)}
            </li>
          ))}
        </ul>
      ) : (
        <DataTable
          columns={cols}
          rows={orders}
          getRowKey={(o) => o.id}
          loading={list.isLoading}
          empty={
            <EmptyState
              compact
              title="No orders"
              description="Orders you add will appear here."
              action={
                canEdit ? <Button onClick={() => setAdding(true)}>New order</Button> : undefined
              }
            />
          }
        />
      )}
      <OrderDialog
        key={reorder?.id ?? String(adding)}
        reorder={reorder}
        last={last}
        pending={open}
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
      <ConfirmDelete
        open={!!deleting}
        name={`the order for ${deleting?.name ?? ""}`}
        noun="order"
        description="It is removed from the list for good. The item's stock is not affected."
        pending={remove.isPending}
        onClose={() => setDeleting(undefined)}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.id, {
            onSuccess: () => toast.success("Order deleted"),
            onError: (e) => toast.error(formErrors(e, []).form ?? "Could not delete the order."),
            onSettled: () => setDeleting(undefined),
          })
        }
      />
      <Dialog open={!!cancelling} onOpenChange={(o) => !o && setCancelling(undefined)}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">
            Cancel the order for {cancelling?.name}?
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            {cancelling?.item
              ? `It was received, so this takes ${qty(cancelling)} back off ${cancelling.item_name}. The order stays in the list as cancelled.`
              : "The order stays in the list as cancelled."}
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Keep it</Button>
            </DialogClose>
            <Button
              variant="destructive"
              disabled={update.isPending}
              onClick={() => cancelling && setStatus(cancelling, "cancelled")}
            >
              Cancel order
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Section>
  );
}
