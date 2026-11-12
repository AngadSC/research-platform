import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { fetchPickerToken, useProviders } from "@/hooks/integrations";
import { pickDriveFile, pickDriveFiles, type PickedFile } from "@/lib/drive";
import { formErrors } from "@/lib/forms";
import { pickerReady } from "@/lib/integrations";

/** Google's own Drive mark, as Google asks it to be shown for "from Drive" actions. */
export function DriveLogo({ className = "size-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 87.3 78" aria-hidden className={className}>
      <path
        d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8h-27.5c0 1.55.4 3.1 1.2 4.5z"
        fill="#0066da"
      />
      <path
        d="m43.65 25-13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-25.4 44a9.06 9.06 0 0 0 -1.2 4.5h27.5z"
        fill="#00ac47"
      />
      <path
        d="m73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5h-27.502l5.852 11.5z"
        fill="#ea4335"
      />
      <path
        d="m43.65 25 13.75-23.8c-1.35-.8-2.9-1.2-4.5-1.2h-18.5c-1.6 0-3.15.45-4.5 1.2z"
        fill="#00832d"
      />
      <path
        d="m59.8 53h-32.3l-13.75 23.8c1.35.8 2.9 1.2 4.5 1.2h50.8c1.6 0 3.15-.45 4.5-1.2z"
        fill="#2684fc"
      />
      <path
        d="m73.4 26.5-12.7-22c-.8-1.4-1.95-2.5-3.3-3.3l-13.75 23.8 16.15 28h27.45c0-1.55-.4-3.1-1.2-4.5z"
        fill="#ffba00"
      />
    </svg>
  );
}

/** "From Drive": opens Google's file picker and hands the chosen file to `onPick` (with
 * `multiple`, once for each chosen file). Hidden when
 * the site has no Google Drive set up; when you have not connected yours, it says how. */
export function FromDriveButton({
  labId,
  onPick,
  size = "sm",
  variant = "outline",
  label = "From Drive",
  disabled,
  quiet,
  multiple,
}: {
  labId: string;
  onPick: (file: PickedFile) => Promise<unknown>;
  size?: "sm" | "default";
  variant?: "outline" | "secondary" | "ghost";
  label?: string;
  disabled?: boolean;
  /** Only chooses the file (a form saves it later), so no "Added" message. */
  quiet?: boolean;
  /** Lets the person choose several files at once. */
  multiple?: boolean;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: providers = [] } = useProviders(labId);
  const [busy, setBusy] = useState(false);
  const drive = providers.find((p) => p.name === "google_drive");
  if (!drive?.configured || !pickerReady(drive)) return null;
  const connected = drive.account?.status === "active";

  const reason = (e: unknown) => {
    const { fields, form } = formErrors(e, ["drive_file_id", "file"]);
    return fields.drive_file_id ?? fields.file ?? form ?? "Google Drive did not answer.";
  };

  async function run() {
    if (!connected) {
      toast.info("Connect Google Drive first, then pick the file.", {
        action: {
          label: "Connect",
          onClick: () => void navigate(`/labs/${labId}/settings/integrations`),
        },
      });
      return;
    }
    setBusy(true);
    try {
      const { access_token: token } = await fetchPickerToken(labId);
      const opts = {
        apiKey: drive!.public_config.api_key!,
        appId: drive!.public_config.app_id!,
        token,
      };
      const files = multiple
        ? await pickDriveFiles(opts)
        : [await pickDriveFile(opts)].filter((f): f is PickedFile => !!f);
      if (!files.length) return;
      // One at a time: each is checked with Drive by the server, and one bad file must not
      // stop the rest.
      let added = 0;
      let lastError: unknown;
      for (const file of files) {
        try {
          await onPick(file);
          added++;
        } catch (e) {
          lastError = e;
        }
      }
      if (added) void qc.invalidateQueries({ queryKey: ["labs", labId] }); // every list that shows files
      if (added < files.length) {
        const why = reason(lastError);
        toast.error(added ? `Added ${added} of ${files.length} files. ${why}` : why);
      } else if (!quiet) {
        toast.success(
          files.length === 1
            ? `Added "${files[0]!.name}" from Drive`
            : `Added ${files.length} files from Drive`,
        );
      }
    } catch (e) {
      toast.error(reason(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button
      type="button"
      variant={variant}
      size={size}
      disabled={busy || disabled}
      onClick={() => void run()}
    >
      <DriveLogo /> {label}
    </Button>
  );
}
