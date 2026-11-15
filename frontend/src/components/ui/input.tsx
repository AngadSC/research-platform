import * as React from "react";
import { cn } from "@/lib/utils";

export function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      className={cn(
        "glass-field flex h-9 w-full rounded-md px-3 py-1 text-sm max-md:h-10 placeholder:text-muted-foreground focus-visible:outline-none disabled:opacity-50 aria-[invalid=true]:border-destructive",
        className,
      )}
      {...props}
    />
  );
}
