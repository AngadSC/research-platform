import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  /** Optional per-page override; the app shell already renders route breadcrumbs. */
  breadcrumbs?: ReactNode;
}

export function PageHeader({ title, description, actions, breadcrumbs }: PageHeaderProps) {
  return (
    <header className="mb-8 flex flex-col gap-2">
      {breadcrumbs}
      {/* Actions drop below the title when both do not fit, instead of squeezing it. */}
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <div className="min-w-0 flex-1 basis-64">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}
