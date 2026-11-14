import { ListPlus, Maximize2, Minimize2, MoreHorizontal } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useBlocker, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { ConflictDialog } from "@/components/documents/ConflictDialog";
import { StaleDocumentBanner } from "@/components/documents/StaleDocumentBanner";
import { RevisionsPanel } from "@/components/documents/RevisionsPanel";
import { LinkedFiles } from "@/components/shared/LinkedFiles";
import {
  MARKED_TOAST,
  ParticipantBadge,
  markLabel,
  useConfirmUnmark,
} from "@/components/shared/ParticipantData";
import { FormField } from "@/components/shared/FormField";
import { FormError } from "@/components/shared/FormError";
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
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useDeleteDocument,
  useDocument,
  useParticipantFlag,
  useSaveDocument,
} from "@/hooks/documents";
import { useMentionPeople } from "@/hooks/mentions";
import { useProject, useTasks } from "@/hooks/projects";
import { useLab } from "@/hooks/workspace";
import { ApiError } from "@/lib/api";
import type { DocumentConflict, DocumentFull } from "@/lib/api-types";
import { useAuth } from "@/hooks/auth";
import { blocksToText } from "@/lib/blocks";
import { NewTaskPanel } from "@/pages/project/NewTaskPanel";
import { formErrors } from "@/lib/forms";
import { cn } from "@/lib/utils";

const RichEditor = lazy(() => import("@/components/documents/RichEditor"));

/** Save this long after the last edit. */
const AUTOSAVE_MS = 3000;
/** The editor and the embed frame fill what the shell and the project header leave. */
const FILL_HEIGHT = "min-h-[calc(100dvh-16rem)]";

/** The tasks that point at this document, and the "add a task from this document" button. The
 * task starts out linked to the document, so its deadline and the manuscript meet. */
function DocumentTasks({
  labId,
  projectId,
  doc,
  canEdit,
}: {
  labId: string;
  projectId: string;
  doc: DocumentFull;
  canEdit: boolean;
}) {
  const tasks = (useTasks(labId, projectId).list.data ?? []).filter((t) =>
    t.documents.some((d) => d.id === doc.id),
  );
  const [adding, setAdding] = useState(false);
  if (!canEdit && tasks.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      {canEdit && (
        <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
          <ListPlus aria-hidden /> Add a task from this document
        </Button>
      )}
      {tasks.map((t) => (
        <Link
          key={t.id}
          to={`/labs/${labId}/projects/${projectId}/tasks?task=${t.id}`}
          className="inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs hover:bg-muted"
        >
          <span className="font-medium">{t.title}</span>
          <span className="text-muted-foreground">
            {t.status === "done" ? "Done" : t.due_date ? `due ${t.due_date}` : "no due date"}
          </span>
        </Link>
      ))}
      {adding && (
        <NewTaskPanel
          labId={labId}
          projectId={projectId}
          document={doc.id}
          title={doc.title}
          onClose={() => setAdding(false)}
        />
      )}
    </div>
  );
}

type Panel = "history" | "retention" | "links" | "delete";
type SaveState = "idle" | "saving" | "saved" | "failed";

function RetentionDialog({
  open,
  onClose,
  canEdit,
  canRetention,
  retainUntil,
  retentionNote,
  onSave,
  saving,
}: {
  open: boolean;
  onClose: () => void;
  canEdit: boolean;
  /** view_retention: without it the fields are read-only and never sent (D55). */
  canRetention: boolean;
  retainUntil: string;
  retentionNote: string;
  onSave: (until: string, note: string) => void;
  saving: boolean;
}) {
  const [until, setUntil] = useState(retainUntil);
  const [note, setNote] = useState(retentionNote);
  const editable = canEdit && canRetention;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Retention</DialogTitle>
        <DialogDescription className="sr-only">How long this document is kept.</DialogDescription>
        <div className="grid gap-3">
          <FormField label="Keep until">
            {(p) => (
              <Input
                {...p}
                type="date"
                value={until}
                readOnly={!editable}
                onChange={(e) => setUntil(e.target.value)}
              />
            )}
          </FormField>
          <FormField label="Retention note">
            {(p) => (
              <Textarea
                {...p}
                value={note}
                readOnly={!editable}
                onChange={(e) => setNote(e.target.value)}
              />
            )}
          </FormField>
        </div>
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">{editable ? "Cancel" : "Close"}</Button>
          </DialogClose>
          {editable && (
            <Button disabled={saving} onClick={() => onSave(until, note)}>
              Save
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function DocumentEditor({
  doc,
  labId,
  projectId,
  canEdit,
  canDelete,
  canRetention,
  onReload,
}: {
  doc: DocumentFull;
  labId: string;
  /** "" for a lab-wide document (D233), which has no retention, linked files or folder. */
  projectId: string;
  canEdit: boolean;
  canDelete: boolean;
  /** view_retention: without it the retention fields are read-only and never sent (D55). */
  canRetention: boolean;
  onReload: () => Promise<void>;
}) {
  const navigate = useNavigate();
  // Focus mode lives in the address, so a reload or a shared link keeps it.
  const [params, setParams] = useSearchParams();
  const focus = params.get("focus") === "1";
  const setFocus = (on: boolean) =>
    setParams(
      (p) => {
        if (on) p.set("focus", "1");
        else p.delete("focus");
        return p;
      },
      { replace: true },
    );
  useEffect(() => {
    if (!focus) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.querySelector('[role="dialog"]')) setFocus(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- setFocus only touches the address
  }, [focus]);
  const save = useSaveDocument(labId, doc.id);
  const people = useMentionPeople(labId, projectId || undefined);
  const { mutateAsync } = save;
  const remove = useDeleteDocument(labId, projectId);
  const { email } = useAuth();
  const [title, setTitle] = useState(doc.title);
  const [flagged, setFlagged] = useState(doc.contains_participant_data);
  const flag = useParticipantFlag(labId);
  const { confirm, dialog } = useConfirmUnmark();
  const toggleFlag = () =>
    flag.mutate(
      { kind: "documents", id: doc.id, value: !flagged },
      {
        onSuccess: () => {
          toast.success(flagged ? "Identifying mark removed" : MARKED_TOAST);
          setFlagged(!flagged);
        },
        onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
      },
    );
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [conflict, setConflict] = useState<DocumentConflict | null>(null);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [retainUntil, setRetainUntil] = useState(doc.retain_until ?? "");
  const [retentionNote, setRetentionNote] = useState(doc.retention_note);
  const [initial] = useState<unknown[]>(() => (Array.isArray(doc.content) ? doc.content : []));
  const content = useRef<unknown[]>(initial);
  const version = useRef(doc.version);
  const [savedVersion, setSavedVersion] = useState(doc.version);
  // Everything a timer or a blocker reads later lives in refs, so a save always sends the latest
  // state, and autosave timers never re-arm from a render.
  const titleRef = useRef(title);
  const retention = useRef({ until: retainUntil, note: retentionNote });
  const dirtyRef = useRef(false);
  const edits = useRef(0); // bumped on every edit; a save only clears `dirty` if nothing came after
  const baseline = useRef(JSON.stringify(initial)); // BlockNote can echo unchanged blocks
  const flight = useRef<Promise<boolean> | null>(null);
  const conflictOpen = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const [leaveFailed, setLeaveFailed] = useState(false);

  const markDirty = useCallback((value: boolean) => {
    dirtyRef.current = value;
    setDirty(value);
  }, []);

  const send = useCallback(
    (autosave: boolean, baseVersion: number = version.current): Promise<boolean> => {
      const sentEdits = edits.current;
      const sentBaseline = JSON.stringify(content.current);
      setSaveState("saving");
      const done = mutateAsync({
        title: titleRef.current.trim() || "Untitled document",
        content: content.current,
        base_version: baseVersion,
        autosave,
        ...(canRetention && {
          retain_until: retention.current.until || null,
          retention_note: retention.current.note,
        }),
      })
        .then(
          (d) => {
            version.current = d.version;
            baseline.current = sentBaseline;
            setSavedVersion(d.version);
            conflictOpen.current = false;
            setConflict(null);
            if (edits.current === sentEdits) {
              markDirty(false);
              setSaveState("saved");
            } else {
              setSaveState("idle"); // a newer edit has its own timer running
            }
            return true;
          },
          (e) => {
            if (e instanceof ApiError && e.status === 409) {
              conflictOpen.current = true;
              setConflict(e.body as DocumentConflict);
              setSaveState("idle");
            } else {
              setSaveState("failed");
              if (!autosave) toast.error(formErrors(e, []).form ?? "Something went wrong.");
            }
            return false;
          },
        )
        .finally(() => {
          flight.current = null;
        });
      flight.current = done;
      return done;
    },
    [mutateAsync, canRetention, markDirty],
  );

  /** Resolves true when nothing is left to save. Autosave pauses while a conflict is open. */
  const flush = useCallback(
    async (autosave: boolean): Promise<boolean> => {
      while (flight.current) await flight.current; // one save at a time, always the latest state
      if (!dirtyRef.current) return true;
      if (!canEdit || conflictOpen.current) return false;
      return send(autosave);
    },
    [canEdit, send],
  );

  const schedule = useCallback(() => {
    edits.current += 1;
    markDirty(true);
    setSaveState((s) => (s === "failed" ? "idle" : s));
    clearTimeout(timer.current);
    timer.current = setTimeout(() => void flush(true), AUTOSAVE_MS);
  }, [flush, markDirty]);

  useEffect(() => () => clearTimeout(timer.current), []);

  // Cmd/Ctrl+S saves now, instead of the browser's "save page" dialog.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        clearTimeout(timer.current);
        void flush(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [flush]);

  // Tab close: warn (the browser's own prompt) while anything is outstanding; try a save once
  // when the tab is hidden, which often lands before the page goes away.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    const onHide = () => {
      if (document.visibilityState === "hidden") void flush(true);
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("visibilitychange", onHide);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("visibilitychange", onHide);
    };
  }, [dirty, flush]);

  // In-app navigation: save on the way out. Only a real failure shows the dialog.
  const blocker = useBlocker(() => dirtyRef.current || !!flight.current);
  const leaving = useRef(false);
  useEffect(() => {
    if (blocker.state !== "blocked" || leaving.current) return;
    leaving.current = true;
    clearTimeout(timer.current);
    void flush(true).then((ok) => {
      leaving.current = false;
      if (ok) blocker.proceed?.();
      else if (conflictOpen.current) blocker.reset?.();
      else setLeaveFailed(true);
    });
  }, [blocker, flush]);

  const reload = async () => {
    clearTimeout(timer.current);
    markDirty(false);
    conflictOpen.current = false;
    setConflict(null);
    await onReload();
  };
  const copyAndReload = async (format: "json" | "text") => {
    const text =
      format === "json"
        ? JSON.stringify({ title, content: content.current }, null, 2)
        : `${title}\n\n${blocksToText(content.current)}`;
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Your changes were copied");
    } catch {
      toast.error("Could not copy to the clipboard. Your changes were not discarded.");
      return;
    }
    await reload();
  };

  // "New document" saves a blank document straight away. If the person leaves without typing
  // anything, soft-delete it (history and audit keep it) rather than leave "Untitled document"
  // behind. Only a never-saved (version 1), untitled, empty, unmarked document qualifies.
  const gone = useRef(false);
  const alive = useRef(true);
  const discardIfBlank = useRef(() => {});
  useEffect(() => {
    discardIfBlank.current = () => {
      if (
        gone.current ||
        !canDelete ||
        doc.created_by.email !== email ||
        doc.embed_url ||
        flagged ||
        version.current !== 1
      )
        return;
      if (dirtyRef.current || doc.title !== "Untitled document" || titleRef.current !== doc.title)
        return;
      if (blocksToText(content.current).trim()) return;
      gone.current = true;
      remove.mutate(doc.id);
    };
  });
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      // Strict mode re-mounts at once; a real leave stays unmounted.
      setTimeout(() => alive.current || discardIfBlank.current(), 0);
    };
  }, []);

  const deleteDocument = () => {
    clearTimeout(timer.current);
    gone.current = true;
    remove.mutate(doc.id, {
      onSuccess: () => {
        markDirty(false);
        toast.success("Document deleted");
        void navigate(
          projectId ? `/labs/${labId}/projects/${projectId}/documents` : `/labs/${labId}/documents`,
        );
      },
      onError: (e) => {
        gone.current = false;
        toast.error(formErrors(e, []).form ?? "Something went wrong.");
      },
    });
  };

  return (
    <div
      className={cn(
        "flex flex-col gap-2",
        // Focus mode: the document takes the whole window, over the sidebar and project header.
        focus ? "fixed inset-0 z-40 overflow-auto bg-background p-3" : FILL_HEIGHT,
      )}
    >
      {dialog}
      <div className="flex items-start gap-2">
        <Input
          aria-label="Title"
          value={title}
          readOnly={!canEdit}
          maxLength={300}
          placeholder="Untitled document"
          className="h-auto flex-1 rounded-sm border-0 bg-transparent px-0 py-1 text-3xl font-semibold focus-visible:ring-1 focus-visible:ring-border"
          onChange={(e) => {
            setTitle(e.target.value);
            titleRef.current = e.target.value;
            schedule();
          }}
        />
        {flagged && (
          <span className="shrink-0 pt-2.5">
            <ParticipantBadge />
          </span>
        )}
        <span aria-live="polite" className="shrink-0 pt-3 text-xs text-muted-foreground">
          {saveState === "saving" && "Saving…"}
          {saveState === "saved" && !dirty && "Saved"}
          {saveState === "failed" && (
            <>
              Couldn’t save.{" "}
              <button type="button" className="underline" onClick={() => void flush(false)}>
                Try again
              </button>
            </>
          )}
        </span>
        <Button
          variant="outline"
          size="sm"
          className="mt-1 shrink-0"
          aria-pressed={focus}
          onClick={() => setFocus(!focus)}
        >
          {focus ? <Minimize2 aria-hidden /> : <Maximize2 aria-hidden />}
          {focus ? "Exit focus" : "Focus"}
        </Button>
        {doc.embed_url && doc.embed_open_url && (
          <Button variant="outline" size="sm" asChild className="mt-1 shrink-0">
            <a href={doc.embed_open_url} target="_blank" rel="noopener noreferrer">
              {doc.embed_url.includes("docs.google.com")
                ? "Open in Google Docs"
                : "Open in Microsoft Office"}
            </a>
          </Button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              aria-label="Document options"
              className="mt-1 shrink-0"
            >
              <MoreHorizontal aria-hidden />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {!canEdit && (
              <>
                <DropdownMenuLabel>You have read-only access.</DropdownMenuLabel>
                <DropdownMenuSeparator />
              </>
            )}
            <DropdownMenuItem onSelect={() => setPanel("history")}>History</DropdownMenuItem>
            {canEdit && (
              <DropdownMenuItem onSelect={() => confirm(flagged, doc.title, toggleFlag)}>
                {markLabel(flagged)}
              </DropdownMenuItem>
            )}
            {projectId && (
              <>
                <DropdownMenuItem onSelect={() => setPanel("retention")}>
                  Retention
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setPanel("links")}>Linked files</DropdownMenuItem>
              </>
            )}
            {canDelete && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => setPanel("delete")}>Delete</DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {projectId && (
        <DocumentTasks labId={labId} projectId={projectId} doc={doc} canEdit={canEdit} />
      )}
      <StaleDocumentBanner
        labId={labId}
        projectId={projectId}
        documentId={doc.id}
        localVersion={savedVersion}
        dirty={dirty}
        onReload={() => void reload()}
      />
      {doc.embed_url ? (
        <iframe
          title={doc.title}
          src={doc.embed_url}
          // Google and Office need scripts, same-origin storage and forms; sign-in prompts and
          // links open in a new, unsandboxed tab.
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
          referrerPolicy="no-referrer"
          className={cn("w-full flex-1 rounded-md border-0", focus ? "min-h-0" : FILL_HEIGHT)}
        />
      ) : (
        <Suspense
          fallback={<Skeleton className={cn("w-full flex-1", focus ? "min-h-0" : FILL_HEIGHT)} />}
        >
          <RichEditor
            initialContent={initial}
            editable={canEdit}
            label="Document content"
            people={people}
            className={cn(
              "flex-1 rounded-none border-0 bg-transparent py-0",
              focus
                ? "[&_.bn-editor]:min-h-[calc(100dvh-5rem)]"
                : "[&_.bn-editor]:min-h-[calc(100dvh-16rem)]", // the whole area takes the click
            )}
            onChange={(b) => {
              content.current = b;
              if (JSON.stringify(b) !== baseline.current) schedule();
            }}
          />
        </Suspense>
      )}
      <ConflictDialog
        conflict={conflict}
        labId={labId}
        documentId={doc.id}
        saving={save.isPending}
        onCopyAndReload={(f) => void copyAndReload(f)}
        onOverwrite={() => conflict && send(false, conflict.current_version)}
        onDismiss={() => {
          conflictOpen.current = false;
          setConflict(null);
        }}
      />
      <RevisionsPanel
        labId={labId}
        documentId={doc.id}
        open={panel === "history"}
        onOpenChange={(o) => setPanel(o ? "history" : null)}
        canEdit={canEdit}
        hasUnsaved={dirty}
        onRestored={() => void reload()}
      />
      {panel === "retention" && (
        <RetentionDialog
          open
          onClose={() => setPanel(null)}
          canEdit={canEdit}
          canRetention={canRetention}
          retainUntil={retainUntil}
          retentionNote={retentionNote}
          saving={save.isPending}
          onSave={(until, note) => {
            if (until === retainUntil && note === retentionNote) {
              setPanel(null);
              return;
            }
            setRetainUntil(until);
            setRetentionNote(note);
            retention.current = { until, note };
            edits.current += 1;
            markDirty(true);
            clearTimeout(timer.current);
            void flush(false).then((ok) => {
              if (ok) setPanel(null);
            });
          }}
        />
      )}
      <Dialog open={panel === "links"} onOpenChange={(o) => !o && setPanel(null)}>
        <DialogContent className="max-w-lg">
          <DialogTitle className="text-base font-semibold">Linked files</DialogTitle>
          <DialogDescription className="sr-only">
            Outside files linked to this document.
          </DialogDescription>
          <LinkedFiles
            labId={labId}
            projectId={projectId}
            canEdit={canEdit}
            target={{ field: "document", id: doc.id }}
          />
        </DialogContent>
      </Dialog>
      <Dialog open={panel === "delete"} onOpenChange={(o) => !o && setPanel(null)}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Delete {title}?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            The document will be removed from this {projectId ? "project" : "lab"}.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button variant="destructive" disabled={remove.isPending} onClick={deleteDocument}>
              Delete document
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog
        open={blocker.state === "blocked" && leaveFailed}
        onOpenChange={(o) => {
          if (!o) {
            setLeaveFailed(false);
            blocker.reset?.();
          }
        }}
      >
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Leave without saving?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            Your latest changes could not be saved. If you leave now they will be lost.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setLeaveFailed(false);
                blocker.reset?.();
              }}
            >
              Stay
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setLeaveFailed(false);
                markDirty(false);
                blocker.proceed?.();
              }}
            >
              Leave
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function DocumentPage() {
  const { labId = "", projectId = "", documentId = "" } = useParams();
  const { data: project } = useProject(labId, projectId);
  const { data: lab } = useLab(labId);
  const { data: doc, error, refetch } = useDocument(labId, documentId);
  const [epoch, setEpoch] = useState(0);
  // A fresh editor per load, so reloads and restores replace the editor's content.
  const reload = useMemo(
    () => async () => {
      await refetch();
      setEpoch((n) => n + 1);
    },
    [refetch],
  );

  if (error) return <FormError message={formErrors(error, []).form} />;
  const owner = projectId ? project : lab; // a lab-wide document follows the lab's permissions
  if (!doc || !owner)
    return (
      <div aria-busy="true" aria-label="Loading" className="grid gap-3">
        <Skeleton className="h-11 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  return (
    <DocumentEditor
      key={`${doc.id}-${epoch}`}
      doc={doc}
      labId={labId}
      projectId={projectId}
      canEdit={owner.my_permissions.includes(projectId ? "edit_content" : "contribute_lab")}
      canDelete={owner.my_permissions.includes(projectId ? "edit_content" : "manage_lab")}
      canRetention={!!projectId && owner.my_permissions.includes("view_retention")}
      onReload={reload}
    />
  );
}
