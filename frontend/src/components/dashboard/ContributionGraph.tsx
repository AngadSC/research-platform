import { useEffect, useMemo, useRef, useState } from "react";
import { FormError } from "@/components/shared/FormError";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useContributions, type DashPerson } from "@/hooks/dashboard";
import {
  buildWeeks,
  dayName,
  KIND_LABELS,
  monthLabels,
  type Cell,
  type KindCounts,
} from "@/lib/contributions";
import { formErrors } from "@/lib/forms";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";

const EVERYONE = "everyone";

// The app's success green at rising strength; it is redefined for dark mode, so both themes work.
const SHADE = [
  "bg-muted",
  "bg-success/25",
  "bg-success/50",
  "bg-success/75",
  "bg-success",
] as const;

const DAY_ROWS = ["", "Mon", "", "Wed", "", "Fri", ""];

function breakdown(k: KindCounts): string {
  return (Object.keys(KIND_LABELS) as (keyof KindCounts)[])
    .filter((key) => k[key] > 0)
    .map((key) => {
      const [one, many] = KIND_LABELS[key];
      return `${k[key]} ${k[key] === 1 ? one : many}`;
    })
    .join(", ");
}

function cellText(c: Cell) {
  return `${c.count === 0 ? "No" : c.count} contribution${c.count === 1 ? "" : "s"} on ${dayName(c.date)}`;
}

/** A GitHub-style year of activity for the lab, or one member picked from the list. */
export function ContributionGraph({ labId, people }: { labId: string; people: DashPerson[] }) {
  const [who, setWho] = useState(EVERYONE);
  const { data, error, isLoading } = useContributions(labId, who === EVERYONE ? undefined : who);
  const [hovered, setHovered] = useState<Cell | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const weeks = useMemo(() => (data ? buildWeeks(data.start, data.end, data.days) : []), [data]);
  const months = useMemo(() => monthLabels(weeks), [weeks]);
  const byDate = useMemo(() => new Map(data?.days.map((d) => [d.date, d]) ?? []), [data]);

  // On a narrow screen, start scrolled to the most recent weeks, as GitHub does.
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [weeks]);

  const name = who === EVERYONE ? "The lab" : (people.find((p) => p.user_id === who)?.name ?? "");
  const shown = hovered ?? null;
  const shownDetail = shown && byDate.get(shown.date);

  return (
    <section aria-labelledby="activity" className="grid gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="activity" className="text-base font-semibold">
            Activity
          </h2>
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {data
              ? `${name}: ${plural(data.total, "contribution")} in the last year`
              : "Contributions in the last year"}
          </p>
        </div>
        <div className="grid gap-1.5">
          <label className="text-sm font-medium" htmlFor="activity-person">
            Person
          </label>
          <Select value={who} onValueChange={setWho}>
            <SelectTrigger id="activity-person" className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={EVERYONE}>Everyone</SelectItem>
              {[...people]
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((p) => (
                  <SelectItem key={p.user_id} value={p.user_id}>
                    {p.name}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="rounded-lg border p-4">
        {error ? (
          <FormError message={formErrors(error, []).form} />
        ) : isLoading || !data ? (
          <Skeleton className="h-[132px] w-full" aria-label="Loading activity" />
        ) : (
          <>
            <div ref={scroller} className="overflow-x-auto pb-1">
              <div
                role="img"
                aria-label={`${name}: ${plural(data.total, "contribution")} between ${dayName(data.start)} and ${dayName(data.end)}${data.total ? `: ${breakdown(data.by_kind)}` : ""}.`}
                className="inline-grid min-w-max grid-cols-[auto_1fr] gap-x-2 text-[11px] text-muted-foreground"
                onMouseLeave={() => setHovered(null)}
              >
                <div />
                <div className="relative h-4">
                  {months.map((m) => (
                    <span
                      key={m.index}
                      className="absolute top-0"
                      style={{ left: `${m.index * 14}px` }}
                    >
                      {m.label}
                    </span>
                  ))}
                </div>
                <div className="grid grid-rows-7 gap-[3px]">
                  {DAY_ROWS.map((label, i) => (
                    <span key={i} className="h-[11px] leading-[11px]">
                      {label}
                    </span>
                  ))}
                </div>
                <div className="flex gap-[3px]">
                  {weeks.map((week) => (
                    <div key={week[0]!.date} className="grid grid-rows-7 gap-[3px]">
                      {week.map((c) => (
                        <span
                          key={c.date}
                          title={c.future ? undefined : cellText(c)}
                          data-level={c.future ? undefined : c.level}
                          data-date={c.date}
                          onMouseEnter={() => !c.future && setHovered(c)}
                          className={cn(
                            "size-[11px] rounded-[2px]",
                            c.future ? "bg-transparent" : SHADE[c.level],
                            c.level === 0 &&
                              !c.future &&
                              "outline outline-1 -outline-offset-1 outline-border/60",
                          )}
                        />
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
              <p className="min-h-4">
                {shown
                  ? `${cellText(shown)}${shownDetail ? `: ${breakdown(shownDetail.by_kind)}` : ""}`
                  : data.total
                    ? `In total: ${breakdown(data.by_kind)}.`
                    : "Nothing yet. Edits, uploads, tasks, updates and chat show up here."}
              </p>
              <div className="flex items-center gap-1" aria-hidden="true">
                <span className="mr-1">Less</span>
                {SHADE.map((s, i) => (
                  <span key={i} className={cn("size-[11px] rounded-[2px]", s)} />
                ))}
                <span className="ml-1">More</span>
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
