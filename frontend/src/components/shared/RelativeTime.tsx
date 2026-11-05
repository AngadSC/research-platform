import { fullDate, relativeTime } from "@/lib/format";

/** Relative time ("in 25 days") with the full local date on hover. */
export function RelativeTime({ value, className }: { value: string; className?: string }) {
  return (
    <time dateTime={value} title={fullDate(value)} className={className}>
      {relativeTime(value)}
    </time>
  );
}
