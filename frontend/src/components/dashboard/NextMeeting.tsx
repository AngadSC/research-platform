import { Video } from "lucide-react";
import { Link } from "react-router";
import { useCalendar } from "@/hooks/admin";
import { addDays } from "@/lib/snooze";
import { localDateISO } from "@/lib/format";

/** The next meeting this person can see, with when it starts and where to join. Nothing if none. */
export function NextMeeting({ labId }: { labId: string }) {
  const today = localDateISO();
  const { list } = useCalendar(labId, today, addDays(today, 30));
  const now = new Date();
  const next = (list.data ?? [])
    .filter((i) => i.kind === "meeting" && i.starts_at && new Date(i.ends_at ?? i.starts_at) > now)
    .sort((a, b) => a.starts_at!.localeCompare(b.starts_at!))[0];
  if (!next) return null;
  const when = new Date(next.starts_at!).toLocaleString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
  return (
    <section
      aria-label="Next meeting"
      className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card p-3 text-sm"
    >
      <div className="min-w-0">
        <p className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
          Next meeting
        </p>
        <Link
          to={`/labs/${labId}/calendar`}
          className="font-medium underline-offset-2 hover:underline"
        >
          {next.title}
        </Link>
        <span className="text-muted-foreground"> · {when}</span>
      </div>
      {next.join_url && (
        <a
          href={next.join_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-primary underline-offset-2 hover:underline"
        >
          <Video className="size-4" aria-hidden /> Join call
        </a>
      )}
    </section>
  );
}
