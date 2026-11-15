import { Link2 } from "lucide-react";
import { STATUS } from "@/lib/participants";
import type { CellStatus } from "@/lib/api-types";
import { cn } from "@/lib/utils";

/** Icon + label, so a status never relies on colour alone. A link icon shows when files exist. */
export function StatusChip({
  status,
  files = 0,
  compact = false,
  className,
}: {
  status: CellStatus;
  files?: number;
  compact?: boolean;
  className?: string;
}) {
  const info = STATUS[status];
  const Icon = info.icon;
  return (
    <span
      title={info.hint}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        info.tone,
        className,
      )}
    >
      <Icon aria-hidden className="size-3.5 shrink-0" />
      <span className={cn(compact && "max-sm:sr-only")}>{info.label}</span>
      {files > 0 && (
        <span className="inline-flex items-center gap-0.5 opacity-80">
          <Link2 aria-hidden className="size-3" />
          <span aria-hidden={files === 1}>{files > 1 ? files : ""}</span>
          <span className="sr-only">{files === 1 ? "1 link" : `${files} links`}</span>
        </span>
      )}
    </span>
  );
}
