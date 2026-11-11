import * as React from "react";
import * as M from "@radix-ui/react-dropdown-menu";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export const DropdownMenu = M.Root;
export const DropdownMenuTrigger = M.Trigger;
export const DropdownMenuRadioGroup = M.RadioGroup;
export const DropdownMenuLabel = (p: React.ComponentProps<typeof M.Label>) => (
  <M.Label {...p} className={cn("px-2 py-1.5 text-xs text-muted-foreground", p.className)} />
);
export const DropdownMenuSeparator = (p: React.ComponentProps<typeof M.Separator>) => (
  <M.Separator {...p} className={cn("-mx-1 my-1 h-px bg-border", p.className)} />
);

export function DropdownMenuContent({
  className,
  sideOffset = 4,
  ...props
}: React.ComponentProps<typeof M.Content>) {
  return (
    <M.Portal>
      <M.Content
        sideOffset={sideOffset}
        className={cn(
          "z-50 min-w-48 rounded-md border bg-popover p-1 text-popover-foreground shadow-sm",
          className,
        )}
        {...props}
      />
    </M.Portal>
  );
}

export function DropdownMenuItem({ className, ...props }: React.ComponentProps<typeof M.Item>) {
  return (
    <M.Item
      className={cn(
        "relative flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none select-none data-[disabled]:opacity-50 data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuRadioItem({
  className,
  children,
  ...props
}: React.ComponentProps<typeof M.RadioItem>) {
  return (
    <M.RadioItem
      className={cn(
        "relative flex cursor-default items-center gap-2 rounded-sm py-1.5 pr-2 pl-8 text-sm outline-none select-none data-[disabled]:opacity-50 data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground",
        className,
      )}
      {...props}
    >
      <M.ItemIndicator className="absolute left-2 inline-flex size-4 items-center justify-center">
        <Check aria-hidden className="size-4" />
      </M.ItemIndicator>
      {children}
    </M.RadioItem>
  );
}
