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
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "mx-auto flex w-full max-w-2xl flex-col items-center justify-center gap-3 rounded-xl border border-dashed bg-muted/30 px-6 py-12 text-center",
        className,
      )}
    >
      {Icon && <Icon className="size-8 text-muted-foreground" />}
      <h2 className="text-base font-semibold">{title}</h2>
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
