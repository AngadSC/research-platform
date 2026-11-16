import type { ComponentType, ReactNode } from "react";
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
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  why,
  action,
  secondary,
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
    </div>
  );
}
