import type { ComponentType, ReactNode } from "react";
import { Link } from "react-router";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: ComponentType<{ className?: string }>;
  title: string;
  description: string;
  /** One line on why this matters, shown under the description. */
  why?: string;
  /** The one primary action, usually a <Button>. */
  action?: ReactNode;
  /** A shortcut beside the primary action, such as importing from Drive. */
  secondary?: ReactNode;
  /** A quiet line at the bottom, such as a link to the getting started checklist. */
  footer?: ReactNode;
  /** Tighter, for an empty list inside a card. */
  compact?: boolean;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  why,
  action,
  secondary,
  footer,
  compact,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex w-full flex-col items-center justify-center gap-2 rounded-xl border bg-card px-6 text-center",
        compact ? "py-6" : "py-10",
        className,
      )}
    >
      {Icon && (
        <span className="mb-1 grid size-10 place-items-center rounded-lg bg-muted text-muted-foreground">
          <Icon className="size-5" />
        </span>
      )}
      <h2 className="text-sm font-semibold">{title}</h2>
      <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
      {why && <p className="max-w-sm text-xs text-muted-foreground">{why}</p>}
      {(action || secondary) && (
        <div className="mt-2 flex flex-wrap justify-center gap-2">
          {action}
          {secondary}
        </div>
      )}
      {footer && <div className="text-xs text-muted-foreground">{footer}</div>}
    </div>
  );
}

/** Home shows the getting started checklist, and a "Show getting started" button if it was hidden. */
export function GettingStartedLink({ labId }: { labId: string }) {
  return (
    <Link to={`/labs/${labId}`} className="underline underline-offset-2 hover:text-foreground">
      Not sure where to begin? See the getting started checklist
    </Link>
  );
}
