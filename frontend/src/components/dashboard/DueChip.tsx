import { Badge } from "@/components/ui/badge";
import { localDateISO } from "@/lib/format";

/** Red "Overdue" once the due date has passed, amber "Due today" on the day; nothing once done.
 * Dates are compared in the viewer's own timezone. */
export function DueChip({ due, status }: { due: string | null | undefined; status: string }) {
  if (!due || status === "done") return null;
  const today = localDateISO();
  if (due < today) return <Badge variant="destructive">Overdue</Badge>;
  if (due === today) return <Badge variant="warning">Due today</Badge>;
  return null;
}
