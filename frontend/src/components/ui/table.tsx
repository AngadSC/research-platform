import * as React from "react";
import { cn } from "@/lib/utils";

export function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div className="relative w-full overflow-x-auto">
      <table className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  );
}
export const TableHeader = (p: React.ComponentProps<"thead">) => (
  <thead {...p} className={cn("[&_tr]:border-b", p.className)} />
);
export const TableBody = (p: React.ComponentProps<"tbody">) => <tbody {...p} />;
export const TableRow = (p: React.ComponentProps<"tr">) => (
  <tr {...p} className={cn("border-b transition-colors hover:bg-muted/50", p.className)} />
);
export const TableHead = (p: React.ComponentProps<"th">) => (
  <th
    {...p}
    className={cn(
      "h-10 px-3 text-left align-middle font-medium text-muted-foreground",
      p.className,
    )}
  />
);
export const TableCell = (p: React.ComponentProps<"td">) => (
  <td {...p} className={cn("px-3 py-3 align-middle", p.className)} />
);
