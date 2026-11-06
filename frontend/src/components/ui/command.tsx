import * as React from "react";
import { Command as CommandPrimitive } from "cmdk";
import { Search } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export function Command({ className, ...props }: React.ComponentProps<typeof CommandPrimitive>) {
  return (
    <CommandPrimitive
      className={cn("flex w-full flex-col overflow-hidden rounded-md bg-popover", className)}
      {...props}
    />
  );
}

export function CommandDialog({
  open,
  onOpenChange,
  children,
  ...commandProps
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
} & Pick<React.ComponentProps<typeof CommandPrimitive>, "value" | "onValueChange">) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[20%] translate-y-0 gap-0 overflow-hidden p-0">
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <DialogDescription className="sr-only">Search for a page or action</DialogDescription>
        <Command {...commandProps}>{children}</Command>
      </DialogContent>
    </Dialog>
  );
}

export function CommandInput({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Input>) {
  return (
    <div className="flex items-center gap-2 border-b px-3">
      <Search className="size-4 opacity-60" aria-hidden />
      <CommandPrimitive.Input
        className={cn(
          "h-11 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground",
          className,
        )}
        {...props}
      />
    </div>
  );
}

export const CommandList = (p: React.ComponentProps<typeof CommandPrimitive.List>) => (
  <CommandPrimitive.List {...p} className={cn("max-h-72 overflow-y-auto p-1", p.className)} />
);
export const CommandEmpty = (p: React.ComponentProps<typeof CommandPrimitive.Empty>) => (
  <CommandPrimitive.Empty {...p} className="py-6 text-center text-sm text-muted-foreground" />
);
export const CommandGroup = (p: React.ComponentProps<typeof CommandPrimitive.Group>) => (
  <CommandPrimitive.Group
    {...p}
    className={cn(
      "overflow-hidden p-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:text-muted-foreground",
      p.className,
    )}
  />
);
export const CommandItem = (p: React.ComponentProps<typeof CommandPrimitive.Item>) => (
  <CommandPrimitive.Item
    {...p}
    className={cn(
      "flex cursor-default items-center gap-2 rounded-sm px-2 py-2 text-sm select-none data-[selected=true]:bg-accent [&_svg]:size-4",
      p.className,
    )}
  />
);
