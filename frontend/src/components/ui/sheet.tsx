import * as React from "react";
import * as SheetPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useFocusReturn } from "./focus-return";

export const Sheet = SheetPrimitive.Root;
export const SheetTrigger = SheetPrimitive.Trigger;
export const SheetTitle = SheetPrimitive.Title;
export const SheetDescription = SheetPrimitive.Description;

export function SheetContent({
  className,
  children,
  onOpenAutoFocus,
  onCloseAutoFocus,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Content>) {
  const returnFocus = useFocusReturn(onOpenAutoFocus, onCloseAutoFocus);
  return (
    <SheetPrimitive.Portal>
      <SheetPrimitive.Overlay className="fixed inset-0 z-50 bg-black/30 backdrop-blur-[3px]" />
      <SheetPrimitive.Content
        className={cn(
          "glass glass--strong glass--solid glass--float glass-slide-in fixed inset-y-3 right-3 z-50 flex h-[calc(100%-1.5rem)] w-[calc(100%-1.5rem)] max-w-md flex-col gap-4 rounded-[var(--radius-dialog)] p-6",
          className,
        )}
        {...returnFocus}
        {...props}
      >
        {children}
        <SheetPrimitive.Close
          aria-label="Close"
          className="absolute top-4 right-4 rounded-sm opacity-70 hover:opacity-100 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <X className="size-4" />
        </SheetPrimitive.Close>
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  );
}
