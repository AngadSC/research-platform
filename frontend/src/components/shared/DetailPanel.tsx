import type { ReactNode } from "react";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";

interface DetailPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
}

/** Right slide-over. Escape and the close button both call onOpenChange(false); focus is trapped. */
export function DetailPanel({
  open,
  onOpenChange,
  title,
  description,
  children,
}: DetailPanelProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <div className="flex flex-col gap-1 pr-6">
          <SheetTitle className="text-lg font-semibold">{title}</SheetTitle>
          <SheetDescription className={description ? "text-sm text-muted-foreground" : "sr-only"}>
            {description ?? title}
          </SheetDescription>
        </div>
        <div className="flex-1 overflow-y-auto">{children}</div>
      </SheetContent>
    </Sheet>
  );
}
