import { useQueryClient } from "@tanstack/react-query";
import { CalendarDays, FolderKanban } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useCurrentLabId, useCurrentProjectId } from "@/hooks/crumbs";
import { useProjects } from "@/hooks/projects";
import { useMe } from "@/hooks/workspace";
import { api } from "@/lib/api";
import { MOD_KEY, OPEN_QUICK_CAPTURE_EVENT } from "@/lib/constants";
import { formErrors } from "@/lib/forms";
import { parseCapture } from "@/lib/quickCapture";

const LAST_KEY = "quick-capture-project";
const readLast = () => {
  try {
    return localStorage.getItem(LAST_KEY) ?? "";
  } catch {
    return "";
  }
};

const dayText = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });

/** One line to a task: "email Dr. Bhalloo Friday #paper2". Opens from the + in the header or
 * with Cmd/Ctrl G, anywhere. The task is yours; the project is the one tagged, else the one you
 * are in, else the one you used last. */
export function QuickCapture() {
  const labId = useCurrentLabId();
  const here = useCurrentProjectId();
  const me = useMe().data;
  const qc = useQueryClient();
  const { data: projects = [] } = useProjects(labId);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [picked, setPicked] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const show = () => setOpen(true);
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "g") {
        e.preventDefault(); // the browser's own "find next"
        setOpen(true);
      }
    };
    window.addEventListener(OPEN_QUICK_CAPTURE_EVENT, show);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener(OPEN_QUICK_CAPTURE_EVENT, show);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  const parsed = useMemo(() => parseCapture(text, projects), [text, projects]);
  const fallback =
    projects.find((p) => p.id === here) ?? projects.find((p) => p.id === readLast()) ?? projects[0];
  const project = parsed.project ?? projects.find((p) => p.id === picked) ?? fallback;
  const unmatched = !!parsed.projectQuery && !parsed.project;

  if (!labId) return null;

  const close = (o: boolean) => {
    setOpen(o);
    if (!o) {
      setText("");
      setPicked("");
      setError(undefined);
    }
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!parsed.title) return setError("Write what needs doing.");
    if (!project) return setError("Make a project first, then add tasks to it.");
    setBusy(true);
    setError(undefined);
    try {
      await api(`/api/labs/${labId}/projects/${project.id}/tasks/`, {
        method: "POST",
        body: {
          title: parsed.title.slice(0, 300),
          due_date: parsed.due,
          ...(me?.id ? { assignee: me.id } : {}),
        },
      });
      try {
        localStorage.setItem(LAST_KEY, project.id);
      } catch {
        /* the last project is a convenience only */
      }
      void qc.invalidateQueries({ queryKey: ["labs", labId] });
      toast.success(`Added to ${project.name}${parsed.due ? `, due ${dayText(parsed.due)}` : ""}`);
      close(false);
    } catch (err) {
      setError(
        formErrors(err, ["title", "due_date", "assignee"]).form ??
          Object.values(formErrors(err, ["title", "due_date", "assignee"]).fields)[0] ??
          "That task could not be added.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-xl">
        <DialogTitle className="text-base font-semibold">Add a task</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Write it in one line. Add a day and <kbd>#project</kbd>, like “email Dr. Bhalloo Friday
          #paper2”.
        </DialogDescription>
        <form onSubmit={submit} className="grid gap-3">
          <Input
            autoFocus
            aria-label="Task"
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={400}
            autoComplete="off"
            placeholder="email Dr. Bhalloo Friday #paper2"
          />
          <div className="flex flex-wrap items-center gap-2 text-xs" aria-live="polite">
            <span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-1">
              <CalendarDays className="size-3.5" aria-hidden />
              {parsed.due ? dayText(parsed.due) : "No due date"}
            </span>
            <span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-1">
              <FolderKanban className="size-3.5" aria-hidden />
              {project ? project.name : "No project"}
            </span>
            {unmatched && (
              <span className="text-destructive">No project matches “#{parsed.projectQuery}”.</span>
            )}
            {projects.length > 1 && !parsed.project && (
              <select
                aria-label="Project"
                value={project?.id ?? ""}
                onChange={(e) => setPicked(e.target.value)}
                className="rounded-md border bg-background px-2 py-1"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            )}
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">{MOD_KEY} G opens this anywhere</span>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={busy || !parsed.title}>
                Add task
              </Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
