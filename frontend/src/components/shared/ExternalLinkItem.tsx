import { ExternalLink as OpenIcon, HardDrive, Link2 } from "lucide-react";
import type { ReactNode } from "react";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Badge } from "@/components/ui/badge";
import type { ExternalLink } from "@/lib/api-types";
import { personName } from "@/lib/api-types";
import { linkState } from "@/lib/integrations";
import { safeHttpUrl } from "@/lib/lineage";

// Keyed by registry icon name and by provider key (links pass `link.provider`).
const ICONS: Record<string, typeof Link2> = { "google-drive": HardDrive, google_drive: HardDrive };

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
          {link.provider === "google_drive" && (
            <span className="text-xs text-muted-foreground">
              Opening this file uses Google&apos;s own sharing settings.
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant={state.tone}>{state.label}</Badge>
        {actions}
      </div>
    </li>
  );
}
