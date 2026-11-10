import {
  BookMarked,
  ClipboardList,
  Cloud,
  ExternalLink as OpenIcon,
  FlaskConical,
  GitBranch,
  HardDrive,
  Archive,
  Link2,
  PenLine,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import type { ExternalLink } from "@/lib/api-types";
import { personName } from "@/lib/api-types";
import { linkState, sharingNote } from "@/lib/integrations";
import { safeHttpUrl } from "@/lib/lineage";

// Neutral icons by category, keyed by the registry icon key (links pass `link.provider`, which
// is the same key for every provider but Drive's older "google-drive" spelling).
const STORAGE = HardDrive;
const ICONS: Record<string, typeof Link2> = {
  "google-drive": STORAGE,
  google_drive: STORAGE,
  onedrive: Cloud,
  dropbox: Cloud,
  box: Cloud,
  github: GitBranch,
  gitlab: GitBranch,
  overleaf: PenLine,
  zotero: BookMarked,
  zenodo: Archive,
  figshare: Archive,
  osf: Archive,
  borealis: Archive,
  frdr: Archive,
  redcap: ClipboardList,
  qualtrics: ClipboardList,
  protocols_io: FlaskConical,
};

export function ProviderIcon({ name, className }: { name: string; className?: string }) {
  const Icon = ICONS[name] ?? Link2;
  return <Icon className={className ?? "size-4 text-muted-foreground"} aria-hidden />;
}

/** One linked outside item: icon, title (opens the item), modified time, who linked it and its
 * status. Reused on the Files tab and in research records. `actions` goes on the right. */
export function ExternalLinkItem({
  link,
  icon,
  actions,
}: {
  link: ExternalLink;
  icon?: string;
  actions?: ReactNode;
}) {
  const state = linkState(link);
  const href = safeHttpUrl(link.url); // null: blank or not http(s), so never rendered as a link
  const modified = link.remote_modified_at ?? link.linked_modified_at;
  const [editing, setEditing] = useState(false);
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-3 py-2 text-sm">
      <div className="flex min-w-0 items-center gap-2">
        <ProviderIcon name={icon ?? link.provider} />
        <div className="grid min-w-0">
          {href ? (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 truncate font-medium hover:underline"
            >
              {link.title}
              <OpenIcon className="size-3 shrink-0" aria-hidden />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          ) : (
            <span className="truncate font-medium">{link.title}</span>
          )}
          <span className="text-xs text-muted-foreground">
            {link.provider_label}
            {modified && (
              <>
                {" | Modified "}
                <RelativeTime value={modified} />
              </>
            )}
            {" | Linked by "}
            {personName(link.linked_by)}
          </span>
          <span className="text-xs text-muted-foreground">
            {sharingNote(link.provider, link.provider_label)}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant={state.tone}>{state.label}</Badge>
        {link.editor_url && (
          <Button
            variant="outline"
            size="sm"
            aria-label={`Edit ${link.title} here`}
            onClick={() => setEditing(true)}
          >
            Edit here
          </Button>
        )}
        {actions}
      </div>
      {editing && <GoogleEditor link={link} onClose={() => setEditing(false)} />}
    </li>
  );
}

/** A Doc or Sheet in Google's own editor (D239). The frame runs on the person's own Google
 * sign-in, and nothing passes through our server. A page cannot tell when Google refuses to be
 * framed, so the way out is always on screen. */
function GoogleEditor({ link, onClose }: { link: ExternalLink; onClose: () => void }) {
  const app = link.editor_url.includes("/spreadsheets/") ? "Google Sheets" : "Google Docs";
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="h-[calc(100dvh-2rem)] max-w-6xl grid-rows-[auto_minmax(0,1fr)] gap-3 p-4">
        <div className="grid gap-1 pr-8">
          <DialogTitle className="truncate text-base font-semibold">{link.title}</DialogTitle>
          <DialogDescription className="text-xs">
            This uses your own Google account, so what you can do here is what Google allows you. If
            it stays blank or asks you to sign in, Google will not show it inside this site:{" "}
            <a
              href={link.editor_url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium underline underline-offset-4"
            >
              Open in {app}
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
            .
          </DialogDescription>
        </div>
        <iframe
          title={link.title}
          src={link.editor_url}
          // The same sandbox as embedded documents (DocumentPage), plus downloads for File > Download.
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-downloads"
          referrerPolicy="no-referrer"
          className="size-full rounded-md border"
        />
      </DialogContent>
    </Dialog>
  );
}
