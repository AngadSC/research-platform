import { Folder as FolderIcon, FolderPlus, MoreHorizontal } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { useCurrentFolder, useFolderActions, useFolders } from "@/hooks/documents";
import type { Folder } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";

const fail = (e: unknown) => toast.error(formErrors(e, []).form ?? "Something went wrong.");

/** Ancestors of `folder` from the top, ending with `folder`. Parents never change, so no cycles. */
function pathOf(folder: Folder, byId: Map<string, Folder>): Folder[] {
  const path = [folder];
  for (let up = folder.parent; up && byId.has(up); up = byId.get(up)!.parent) {
    path.unshift(byId.get(up)!);
  }
  return path;
}

function byIdMap(folders: Folder[]) {
  return new Map(folders.map((f) => [f.id, f]));
}

type Editing =
  { mode: "new" } | { mode: "rename"; folder: Folder } | { mode: "delete"; folder: Folder };

/** Breadcrumb, subfolder rows and new/rename/delete for the folder being browsed. */
export function FolderBrowser({
  labId,
  projectId,
  canEdit,
}: {
  labId: string;
  projectId: string;
  canEdit: boolean;
}) {
  const current = useCurrentFolder();
  const { data: folders = [] } = useFolders(labId, projectId);
  const { create, rename, remove } = useFolderActions(labId, projectId);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [name, setName] = useState("");
  const byId = useMemo(() => byIdMap(folders), [folders]);
  const here = current ? byId.get(current) : undefined;
  const children = folders.filter((f) => (f.parent ?? null) === (current ?? null));
  const close = () => setEditing(null);
  const crumbs = here
    ? [
        { label: "All", to: "." },
        ...pathOf(here, byId).map((f) => ({ label: f.name, to: `?folder=${f.id}` })),
      ]
    : [{ label: "All" }];

  const save = (e: FormEvent) => {
    e.preventDefault();
    const handlers = { onSuccess: close, onError: fail };
    if (editing?.mode === "new") create.mutate({ name, parent: current }, handlers);
    if (editing?.mode === "rename") rename.mutate({ id: editing.folder.id, name }, handlers);
  };

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Breadcrumbs items={crumbs} label="Folders" />
        {canEdit && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setName("");
              setEditing({ mode: "new" });
            }}
          >
            <FolderPlus aria-hidden /> New folder
          </Button>
        )}
      </div>
      {children.length > 0 && (
        <ul aria-label="Folders in this folder" className="divide-y rounded-lg border">
          {children.map((f) => (
            <li key={f.id} className="flex items-center gap-2 px-3 py-1.5 text-sm">
              <FolderIcon aria-hidden className="size-4 text-muted-foreground" />
              <Link
                to={`?folder=${f.id}`}
                className="min-w-0 flex-1 truncate font-medium hover:underline"
              >
                {f.name}
              </Link>
              {canEdit && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="sm" aria-label={`Actions for ${f.name}`}>
                      <MoreHorizontal aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem
                      onSelect={() => {
                        setName(f.name);
                        setEditing({ mode: "rename", folder: f });
                      }}
                    >
                      Rename
                    </DropdownMenuItem>
                    <DropdownMenuItem onSelect={() => setEditing({ mode: "delete", folder: f })}>
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </li>
          ))}
        </ul>
      )}
      <Dialog
        open={editing?.mode === "new" || editing?.mode === "rename"}
        onOpenChange={(o) => !o && close()}
      >
        <DialogContent>
          <DialogTitle className="text-base font-semibold">
            {editing?.mode === "new" ? "New folder" : "Rename folder"}
          </DialogTitle>
          <DialogDescription className="sr-only">
            {editing?.mode === "new" ? "Create a folder here." : "Give this folder a new name."}
          </DialogDescription>
          <form onSubmit={save} className="grid gap-3">
            <FormField label="Name">
              {(p) => (
                <Input
                  {...p}
                  autoFocus
                  required
                  maxLength={200}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              )}
            </FormField>
            <div className="flex justify-end gap-2">
              <DialogClose asChild>
                <Button variant="outline" type="button">
                  Cancel
                </Button>
              </DialogClose>
              <Button type="submit" disabled={create.isPending || rename.isPending}>
                Save
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog open={editing?.mode === "delete"} onOpenChange={(o) => !o && close()}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">
            Delete {editing?.mode === "delete" ? editing.folder.name : ""}?
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            Its documents, files and subfolders move up one level. Nothing is lost.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() =>
                editing?.mode === "delete" &&
                remove.mutate(editing.folder.id, { onSuccess: close, onError: fail })
              }
            >
              Delete folder
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export interface Movable {
  kind: "documents" | "attachments";
  id: string;
  name: string;
  folder: string | null;
}

/** "Move to": a plain select over the whole tree, with the full path of each folder. */
export function MoveDialog({
  labId,
  projectId,
  item,
  onClose,
}: {
  labId: string;
  projectId: string;
  item: Movable | null;
  onClose: () => void;
}) {
  const { data: folders = [] } = useFolders(labId, projectId);
  const { move } = useFolderActions(labId, projectId);
  const [target, setTarget] = useState<string>("");
  const options = useMemo(() => {
    const byId = byIdMap(folders);
    return folders
      .map((f) => ({
        id: f.id,
        label: pathOf(f, byId)
          .map((p) => p.name)
          .join(" / "),
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [folders]);

  return (
    <Dialog
      open={!!item}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
    >
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Move {item?.name}</DialogTitle>
        <DialogDescription className="sr-only">Choose a folder for this item.</DialogDescription>
        <FormField label="Folder">
          {(p) => (
            <select
              {...p}
              className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              value={target || item?.folder || ""}
              onChange={(e) => setTarget(e.target.value)}
            >
              <option value="">Project top level</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          )}
        </FormField>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={move.isPending}
            onClick={() =>
              item &&
              move.mutate(
                { kind: item.kind, id: item.id, folder: target || item.folder || null },
                {
                  onSuccess: () => {
                    toast.success("Moved");
                    onClose();
                  },
                  onError: fail,
                },
              )
            }
          >
            Move
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
