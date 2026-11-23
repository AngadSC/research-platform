import { ChevronRight } from "lucide-react";
import { useLayoutEffect, useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * A section that starts folded: a quiet heading with a count or hint, and everything else behind
 * it. Built on <details>, so it works from the keyboard and its content stays in the page.
 */
export function Disclosure({
  title,
  hint,
  defaultOpen = false,
  level = 2,
  card = false,
  region = false,
  firstOpen = false,
  className,
  children,
}: {
  title: string;
  /** Short text beside the title (a count, or what is inside). */
  hint?: ReactNode;
  defaultOpen?: boolean;
  level?: 2 | 3;
  /** Wear a card around it, to sit among other cards. */
  card?: boolean;
  /** Make it a named region, for a section that people may jump to or that tests look up. */
  region?: boolean;
  /** Opens by itself when it is the first folded section in its group, so a page never looks empty. */
  firstOpen?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const Heading = level === 2 ? "h2" : "h3";
  const ref = useRef<HTMLDetailsElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!firstOpen || !el) return;
    const before = el.previousElementSibling;
    if (!(before instanceof HTMLElement && before.dataset.disc)) el.open = true;
  }, [firstOpen]);
  return (
    <details
      ref={ref}
      data-disc=""
      open={defaultOpen || undefined}
      role={region ? "region" : undefined}
      aria-label={region ? title : undefined}
      className={cn(
        "group/disc",
        card && "rounded-xl border bg-card px-5 py-3 shadow-[var(--shadow-glass-1)]",
        className,
      )}
    >
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-2 rounded-md py-1 [&::-webkit-details-marker]:hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
        <ChevronRight
          aria-hidden
          className="size-4 shrink-0 text-muted-foreground transition-transform group-open/disc:rotate-90"
        />
        <Heading className="text-base font-semibold">{title}</Heading>
        {hint && (
          <span className="w-full min-w-0 pl-6 text-sm text-muted-foreground @xl:w-auto @xl:pl-0">
            {hint}
          </span>
        )}
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}
