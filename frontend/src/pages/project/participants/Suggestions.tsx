import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface Suggestion {
  id: string;
  text: string;
  action: string;
  run: () => void;
}

/** Offers drawn from the data on the page. Each is one tap to accept or dismiss, never automatic. */
export function Suggestions({
  items,
  onDismiss,
}: {
  items: Suggestion[];
  onDismiss: (id: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <ul aria-label="Suggestions" className="grid gap-2">
      {items.slice(0, 2).map((s) => (
        <li
          key={s.id}
          className="flex flex-wrap items-center gap-2 rounded-xl border bg-card px-3 py-2 text-sm"
        >
          <span className="min-w-0 flex-1">{s.text}</span>
          <Button size="sm" onClick={s.run}>
            {s.action}
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label={`Dismiss: ${s.text}`}
            onClick={() => onDismiss(s.id)}
          >
            <X aria-hidden />
          </Button>
        </li>
      ))}
    </ul>
  );
}
