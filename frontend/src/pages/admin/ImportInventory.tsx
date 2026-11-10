import { useState } from "react";
import { toast } from "sonner";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { importInventory } from "@/hooks/admin";
import { useQueryClient } from "@tanstack/react-query";
import type { InventoryImportResult } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";

type Row = InventoryImportResult["rows"][number];

/** Inventory from a CSV (D229): a preview first, and the whole file or nothing. */
export function ImportInventory({ labId }: { labId: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<InventoryImportResult | null>(null);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  function close() {
    setOpen(false);
    setFile(null);
    setPreview(null);
    setError(undefined);
  }

  async function run(commit: boolean) {
    if (!file) return;
    setBusy(true);
    setError(undefined);
    try {
      const out = await importInventory(labId, file, commit);
      if (commit) {
        await qc.invalidateQueries({ queryKey: ["labs", labId, "inventory"] });
        toast.success(`Added ${out.imported} items.`);
        close();
      } else {
        setPreview(out);
      }
    } catch (err) {
      setPreview(null);
      setError(formErrors(err, []).form ?? "We could not read that file.");
    } finally {
      setBusy(false);
    }
  }

  const cols: Column<Row>[] = [
    { key: "row", header: "Line", cell: (r) => r.row },
    { key: "name", header: "Name", cell: (r) => r.name },
    { key: "qty", header: "Quantity", cell: (r) => `${r.quantity} ${r.unit}`.trim() },
    {
      key: "issue",
      header: "Problems",
      cell: (r) => {
        const issues = Object.entries(r.errors).map(([k, v]) => `${k}: ${v}`);
        if (issues.length > 0) return <span className="text-destructive">{issues.join(" ")}</span>;
        return r.warning || "Ready";
      },
    },
  ];

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        Import CSV
      </Button>
      <Dialog open={open} onOpenChange={(o) => !o && close()}>
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
          <DialogTitle className="text-base font-semibold">
            Import inventory from a file
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            A CSV file with a first row of column names, including Name and Category. Up to 1000
            rows, 1 MB at most. Nothing is added until you confirm, and if any row has a problem
            nothing is added at all.
          </DialogDescription>
          <FormField label="CSV file">
            {(p) => (
              <Input
                {...p}
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setPreview(null);
                  setError(undefined);
                }}
              />
            )}
          </FormField>
          <FormError message={error} />
          {preview && (
            <div className="grid gap-2">
              <p className="text-sm">
                {preview.valid} ready, {preview.invalid} with problems.
              </p>
              {preview.ignored_columns.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Ignored columns: {preview.ignored_columns.join(", ")}.
                </p>
              )}
              <DataTable
                columns={cols}
                rows={preview.rows}
                getRowKey={(r) => String(r.row)}
                loading={false}
                empty={<span className="text-sm">No rows in this file.</span>}
              />
            </div>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" onClick={close}>
              Cancel
            </Button>
            {!preview && (
              <Button type="button" disabled={!file || busy} onClick={() => void run(false)}>
                Preview
              </Button>
            )}
            {preview && (
              <Button
                type="button"
                disabled={busy || preview.invalid > 0 || preview.valid === 0}
                onClick={() => void run(true)}
              >
                Import {preview.valid} items
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
