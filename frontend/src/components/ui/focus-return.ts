import * as React from "react";

/** The trigger of the most recently used dropdown menu: dialogs opened from a menu item return here,
 * because the item itself is gone by the time the dialog closes. */
let lastMenuOpener: HTMLElement | null = null;
export function rememberMenuOpener(el: HTMLElement) {
  lastMenuOpener = el; // not document.activeElement: Radix does not always focus the trigger on click
}

/** For a dialog or sheet: remembers what had focus when it opened and puts focus back there when it
 * closes (Radix only does that when a Trigger is inside the same Root). Spread the result on the Content. */
export function useFocusReturn(
  onOpenAutoFocus?: (e: Event) => void,
  onCloseAutoFocus?: (e: Event) => void,
) {
  const opener = React.useRef<Element | null>(null);
  return {
    onOpenAutoFocus(e: Event) {
      opener.current = document.activeElement; // focus has not moved into the dialog yet
      onOpenAutoFocus?.(e);
    },
    onCloseAutoFocus(e: Event) {
      onCloseAutoFocus?.(e);
      if (e.defaultPrevented) return;
      const o = opener.current;
      const el =
        o instanceof HTMLElement && o !== document.body && o.isConnected ? o : lastMenuOpener;
      if (el?.isConnected) {
        e.preventDefault();
        el.focus();
      }
    },
  };
}
