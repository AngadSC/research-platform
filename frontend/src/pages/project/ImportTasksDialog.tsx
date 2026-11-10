import { useState } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useImportTasks, useTaskSources } from "@/hooks/integrations";
import type { IntegrationProvider } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";

/** Copy tasks from a connected task app into this project. Only shown once one is connected. */
export function ImportTasksDialog({
  labId,
  projectId,
  services,
  onClose,
}: {
  labId: string;
  projectId: string;
  services: IntegrationProvider[];
  onClose: () => void;
}) {
  const [name, setName] = useState(services[0]?.name ?? "");
  const [source, setSource] = useState("");
  const [failure, setFailure] = useState<string>();
  const sources = useTaskSources(labId, name);
  const run = useImportTasks(labId, projectId);

  const submit = () => {
    setFailure(undefined);
    run.mutate(
      { provider: name, source },
      {
        onSuccess: (r) => {
          toast.success(
            `Added ${r.created} ${r.created === 1 ? "task" : "tasks"}` +
              (r.skipped ? `. ${r.skipped} were already here.` : "."),
          );
          onClose();
        },
        onError: (e) => setFailure(formErrors(e, ["source"]).form ?? "Something went wrong."),
      },
    );
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Import tasks</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Copies open tasks into this project, unassigned. Nothing changes in the other app, and
          tasks with a title already in this project are left out.
        </DialogDescription>
        <FormError message={failure} />
        {services.length > 1 && (
          <FormField label="Service">
            {(props) => (
              <Select
                value={name}
                onValueChange={(v) => {
                  setName(v);
                  setSource("");
                }}
              >
                <SelectTrigger {...props}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {services.map((p) => (
                    <SelectItem key={p.name} value={p.name}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </FormField>
        )}
        <FormField
          label="List to import"
          hint={sources.isError ? "Could not load your lists." : undefined}
        >
          {(props) => (
            <Select value={source} onValueChange={setSource} disabled={!sources.data?.length}>
              <SelectTrigger {...props}>
                <SelectValue placeholder={sources.isLoading ? "Loading" : "Choose a list"} />
              </SelectTrigger>
              <SelectContent>
                {sources.data?.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </FormField>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!source || run.isPending}>
            Import
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
