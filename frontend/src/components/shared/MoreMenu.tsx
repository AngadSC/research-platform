import { MoreHorizontal } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export interface MoreItem {
  label: string;
  icon?: ReactNode;
  onSelect: () => void;
  /** Left out when false, so callers can write `show && {...}` in a list. */
  disabled?: boolean;
}

/**
 * The secondary actions of a page behind one quiet "⋯" button, so the page shows its one main
 * action and the rest are a click away.
 */
export function MoreMenu({
  items,
  label = "More actions",
}: {
  items: (MoreItem | false | null | undefined)[];
  label?: string;
}) {
  const list = items.filter((i): i is MoreItem => !!i);
  if (list.length === 0) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={label} title={label}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-48">
        {list.map((i) => (
          <DropdownMenuItem key={i.label} disabled={i.disabled} onSelect={i.onSelect}>
            {i.icon}
            {i.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
