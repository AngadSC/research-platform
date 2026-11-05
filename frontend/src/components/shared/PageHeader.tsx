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
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}
