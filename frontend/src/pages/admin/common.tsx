import type { ComponentProps, ReactNode } from "react";
import { Disclosure } from "@/components/shared/Disclosure";
import { cn } from "@/lib/utils";

export function Section({
  title,
  description,
  defaultOpen,
  children,
}: {
  title: string;
  description?: string;
  /** Starts open, for the one thing a page is for. */
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  // Folded to its title and one line about it; the rest opens on demand.
  return (
    <Disclosure card region firstOpen defaultOpen={defaultOpen} title={title} hint={description}>
      <div className="grid gap-4">{children}</div>
    </Disclosure>
  );
}

/** A native select styled like Input: simple, accessible and easy to test. */
export function NativeSelect({ className, ...props }: ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "glass-field flex h-9 w-full rounded-md px-3 py-1 text-sm max-md:h-10 focus-visible:outline-none disabled:opacity-50 aria-[invalid=true]:border-destructive",
        className,
      )}
      {...props}
    />
  );
}

export const formValue = (fd: FormData, key: string) => String(fd.get(key) ?? "").trim();
