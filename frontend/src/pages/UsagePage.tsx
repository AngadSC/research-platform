import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { PageHeader } from "@/components/shared/PageHeader";
import { Segmented } from "@/components/shared/Segmented";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useMe } from "@/hooks/workspace";
import { api } from "@/lib/api";
import type { SiteUsage } from "@/lib/api-types";
import { shortDate } from "@/lib/format";
import { NotFoundPage } from "@/pages/HomePage";

type Window = "7" | "30" | "90";
type Series = "active_users" | "sign_ins" | "signups";
const SERIES: { value: Series; label: string }[] = [
  { value: "active_users", label: "Active people" },
  { value: "sign_ins", label: "Sign-ins" },
  { value: "signups", label: "Sign-ups" },
];

/** D379: site staff only. Everyone else gets "Page not found", as the API answers them. */
export function UsagePage() {
  const me = useMe().data;
  const [days, setDays] = useState<Window>("30");
  const [includeTest, setIncludeTest] = useState(false);
  const usage = useQuery({
    queryKey: ["usage", days, includeTest],
    queryFn: () => api<SiteUsage>(`/api/usage/?days=${days}&include_test=${includeTest ? 1 : 0}`),
    enabled: !!me?.site_staff,
    placeholderData: (prev) => prev,
  });
  if (me && !me.site_staff) return <NotFoundPage />;
  const data = usage.data;
  return (
    <div className="grid gap-8">
      <PageHeader
        title="Usage"
        description="How people use labbenchos across every lab. Only site staff see this page. Days are in UTC."
        actions={
          <>
            <Segmented
              label="Time window"
              value={days}
              onChange={setDays}
              options={[
                { value: "7", label: "7 days" },
                { value: "30", label: "30 days" },
                { value: "90", label: "90 days" },
              ]}
            />
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includeTest}
                onChange={(e) => setIncludeTest(e.target.checked)}
              />
              Include test and staff accounts
            </label>
          </>
        }
      />
      {usage.isError ? (
        <p role="alert" className="text-sm text-destructive">
          {usage.error.message}
        </p>
      ) : !data ? (
        <div className="grid gap-4" aria-busy="true" aria-label="Loading">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
          <Skeleton className="h-48" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <UsageReport data={data} />
      )}
    </div>
  );
}

function UsageReport({ data }: { data: SiteUsage }) {
  const h = data.headline;
  return (
    <>
      <section aria-label="Summary" className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="People" value={h.total_users} />
        <Tile label={`New sign-ups (${data.days} days)`} value={h.new_users} />
        <Tile label={`Active people (${data.days} days)`} value={h.active_users} />
        <Tile label="Labs" value={h.labs_total} note={`${h.labs_new} new`} />
        <Tile label="Projects" value={h.projects_total} />
        <Tile label="Active today" value={h.dau} />
        <Tile label="Active this week" value={h.wau} note="last 7 days" />
        <Tile label="Active this month" value={h.mau} note="last 30 days" />
      </section>
      <DailyChart daily={data.daily} />
      <Section
        title="New sign-ups: how far they got"
        hint="Of the people who signed up in this window. Each step is counted on its own."
      >
        <ul className="grid gap-3">
          {data.funnel.map((s) => (
            <li key={s.key} className="grid gap-1">
              <div className="flex justify-between text-sm">
                <span>{s.label}</span>
                <span className="text-muted-foreground tabular-nums">
                  {s.count} · {s.percent}%
                </span>
              </div>
              <Bar percent={s.percent} />
            </li>
          ))}
        </ul>
      </Section>
      <Section title="What people use" hint="In this window: actions taken and how many people.">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Feature</TableHead>
              <TableHead className="text-right">Actions</TableHead>
              <TableHead className="text-right">People</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.features.map((f) => (
              <TableRow key={f.feature} className={f.events ? "" : "text-muted-foreground"}>
                <TableCell>{f.feature}</TableCell>
                <TableCell className="text-right tabular-nums">{f.events}</TableCell>
                <TableCell className="text-right tabular-nums">{f.users}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {data.integrations.length > 0 && (
          <p className="mt-3 text-sm text-muted-foreground">
            Connected:{" "}
            {data.integrations
              .map((i) => `${i.provider} ${i.connections} (${i.users} people)`)
              .join(", ")}
          </p>
        )}
      </Section>
      <Section title="Recent sign-ups" hint="The newest 50 in this window.">
        {data.recent_signups.length === 0 ? (
          <p className="text-sm text-muted-foreground">No one signed up in this window.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Institution</TableHead>
                <TableHead>Joined</TableHead>
                <TableHead className="text-right">Labs</TableHead>
                <TableHead>Last active</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.recent_signups.map((u) => (
                <TableRow key={u.id}>
                  <TableCell>{u.display_name || "—"}</TableCell>
                  <TableCell>{u.email}</TableCell>
                  <TableCell>{u.institution || "—"}</TableCell>
                  <TableCell>{shortDate(u.date_joined)}</TableCell>
                  <TableCell className="text-right tabular-nums">{u.labs}</TableCell>
                  <TableCell>{u.last_active ? shortDate(u.last_active) : "Never"}</TableCell>
                  <TableCell className="text-right tabular-nums">{u.events}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
      <Section
        title="Do they come back?"
        hint="People grouped by the week they signed up (weeks start Monday), and the share active in each week after."
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Signed up the week of</TableHead>
              <TableHead className="text-right">People</TableHead>
              {Array.from({ length: data.retention.length - 1 }, (_, i) => (
                <TableHead key={i} className="text-right">
                  Week {i + 1}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.retention.map((c) => (
              <TableRow key={c.week_start}>
                <TableCell>{shortDate(c.week_start)}</TableCell>
                <TableCell className="text-right tabular-nums">{c.users}</TableCell>
                {Array.from({ length: data.retention.length - 1 }, (_, i) => (
                  <TableCell key={i} className="text-right tabular-nums">
                    {c.weeks[i] == null ? "" : `${c.weeks[i]}%`}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>
    </>
  );
}

function Tile({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {note && <div className="text-xs text-muted-foreground">{note}</div>}
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <section className="grid gap-3">
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground">{hint}</p>
      </div>
      {children}
    </section>
  );
}

function Bar({ percent }: { percent: number }) {
  return (
    <div className="h-2 rounded-full bg-muted">
      <div
        className="h-2 rounded-full bg-primary"
        style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
      />
    </div>
  );
}

function DailyChart({ daily }: { daily: SiteUsage["daily"] }) {
  const [series, setSeries] = useState<Series>("active_users");
  const label = SERIES.find((s) => s.value === series)!.label;
  const peak = Math.max(0, ...daily.map((d) => d[series]));
  const max = Math.max(1, peak);
  const [first, last] = [daily[0], daily.at(-1)];
  return (
    <section className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Day by day</h2>
        <Segmented label="Show" value={series} onChange={setSeries} options={SERIES} />
      </div>
      <ol
        aria-label={`${label} per day`}
        className="flex h-40 items-end gap-px rounded-lg border p-3"
      >
        {daily.map((d) => {
          const text = `${shortDate(d.date)}: ${d[series]} ${label.toLowerCase()}`;
          return (
            <li
              key={d.date}
              aria-label={text}
              title={text}
              className="flex h-full flex-1 items-end"
            >
              <div
                className="w-full rounded-t-sm bg-primary"
                style={{ height: `${(100 * d[series]) / max}%`, minHeight: d[series] ? 2 : 0 }}
              />
            </li>
          );
        })}
      </ol>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{first && shortDate(first.date)}</span>
        <span>Most in a day: {peak}</span>
        <span>{last && shortDate(last.date)}</span>
      </div>
    </section>
  );
}
