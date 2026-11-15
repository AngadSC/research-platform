import * as React from "react";
import { cn } from "@/lib/utils";

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "glass-field flex min-h-20 w-full rounded-md px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none disabled:opacity-50 aria-[invalid=true]:border-destructive",
        className,
      )}
      {...props}
    />
  );
}
