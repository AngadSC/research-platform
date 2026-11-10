import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useZoteroImport, useZoteroItems } from "@/hooks/papers";
import { formErrors } from "@/lib/forms";

const MAX = 20;

/** Pick papers from your own Zotero library and copy their details (never the PDFs) in. */
export function ZoteroImportDialog({ labId, onClose }: { labId: string; onClose: () => void }) {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [failure, setFailure] = useState<string>();
  const items = useZoteroItems(labId, query);
  const run = useZoteroImport(labId);

  const toggle = (id: string) =>
    setPicked((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  const search = (e: FormEvent) => {
    e.preventDefault();
    setQuery(text.trim());
    setPicked([]);
  };
  const submit = () => {
    setFailure(undefined);
    run.mutate(picked.slice(0, MAX), {
      onSuccess: (r) => {
        toast.success(
          `Added ${r.created} ${r.created === 1 ? "paper" : "papers"}` +
            (r.skipped ? `. ${r.skipped} were skipped: already here or not a paper.` : "."),
        );
        onClose();
      },
      onError: (e) => setFailure(formErrors(e, ["ids"]).form ?? "Something went wrong."),
    });
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Import from Zotero</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Copies the title, authors, year, journal, DOI and abstract into the lab&apos;s library.
          PDFs stay in Zotero.
        </DialogDescription>
        <FormError message={failure} />
        <form onSubmit={search} className="flex items-end gap-2">
          <div className="min-w-0 flex-1">
            <FormField label="Search your library">
              {(p) => (
                <Input
                  {...p}
                  type="search"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                />
              )}
            </FormField>
          </div>
          <Button type="submit" variant="outline">
            Search
          </Button>
        </form>
        {items.isLoading && <p className="text-sm text-muted-foreground">Loading</p>}
        {items.isError && (
          <p className="text-sm text-muted-foreground">
            Could not reach Zotero. Try again shortly.
          </p>
        )}
        {items.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">Nothing found in your library.</p>
        )}
        <ul className="grid max-h-72 gap-1 overflow-y-auto">
          {items.data?.map((item) => (
            <li key={item.id}>
              <label className="flex cursor-pointer items-start gap-2 rounded-md p-2 text-sm hover:bg-muted">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={picked.includes(item.id)}
                  disabled={!picked.includes(item.id) && picked.length >= MAX}
                  onChange={() => toggle(item.id)}
                />
                <span className="min-w-0">
                  <span className="block font-medium">{item.title}</span>
                  {item.subtitle && (
                    <span className="block text-xs text-muted-foreground">{item.subtitle}</span>
                  )}
                </span>
              </label>
            </li>
          ))}
        </ul>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!picked.length || run.isPending}>
            Import {picked.length || ""}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
