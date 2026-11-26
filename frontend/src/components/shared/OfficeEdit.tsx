import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useAccounts, useConnect, useProviders } from "@/hooks/integrations";
import type { Attachment } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";

/** The OneDrive permission Edit in Office needs. Asked for only when the person clicks for it. */
export const OFFICE_EDIT_SCOPE = "Files.ReadWrite.AppFolder";

/** "Edit in Word, Excel or PowerPoint": copies an upload into a labbenchos folder in the person's
 * own OneDrive, where it opens in Office on the web. When OneDrive is not connected, or not yet
 * allowed to save files, it says so and offers that step instead. `available` is false when the
 * site has no OneDrive set up. */
export function useOfficeEdit(labId: string, copy: (id: string) => Promise<Attachment>) {
  const { data: providers = [] } = useProviders(labId);
  const onedrive = providers.find((p) => p.name === "onedrive");
  const { data: accounts = [] } = useAccounts(labId, false, !!onedrive?.configured);
  const connect = useConnect(labId);
  const [asking, setAsking] = useState<{ app: string; connected: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const mine = accounts.find((a) => a.provider === "onedrive" && a.status === "active");
  const scopes = mine?.granted_scopes; // a JSON list in the schema, so typed as unknown
  const allowed = Array.isArray(scopes) && scopes.includes(OFFICE_EDIT_SCOPE);

  async function start(file: Attachment, app: string) {
    if (!allowed) return setAsking({ app, connected: !!mine });
    setBusy(true);
    try {
      const made = await copy(file.id);
      toast.success("Copied to your OneDrive. Changes there do not change the original.", {
        action: {
          label: `Open in ${app}`,
          onClick: () => window.open(made.external_url, "_blank", "noopener"),
        },
      });
    } catch (e) {
      toast.error(formErrors(e, []).form ?? "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const allow = () =>
    connect.mutate(
      // The read permissions it already has, plus saving to its own folder.
      { provider: "onedrive", body: { scopes: onedrive?.scopes ?? [] } },
      { onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong.") },
    );

  const dialog = asking && (
    <Dialog open onOpenChange={(open) => !open && setAsking(null)}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Edit in {asking.app}</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          {asking.connected
            ? "Microsoft will ask you to let labbenchos save files in its own folder in your OneDrive. "
            : "Connect your OneDrive first. "}
          We put a copy of the file in that folder and you edit it in {asking.app} on the web.
          Changes there do not change the original here.
        </DialogDescription>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setAsking(null)}>
            Cancel
          </Button>
          <Button disabled={connect.isPending} onClick={allow}>
            {asking.connected ? "Allow editing in Office" : "Connect OneDrive"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );

  return { available: !!onedrive?.configured, busy, start, dialog };
}
