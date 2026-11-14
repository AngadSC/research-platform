/** One docked panel at a time: opening either side panel announces itself here, and the other
 * one closes (it keeps its remembered width). */
export const PANEL_OPENED = "labbenchos:panel-opened";
export type PanelName = "assistant" | "google";
export const announcePanel = (name: PanelName) =>
  window.dispatchEvent(new CustomEvent(PANEL_OPENED, { detail: name }));

const SIDEBAR_W = 256; // w-64
const MAIN_MIN = 640; // the page beside a docked panel keeps at least this much

/** The widest a docked panel may be: the window minus the sidebar minus the room the page needs. */
export const dockCap = (min: number) => Math.max(min, window.innerWidth - SIDEBAR_W - MAIN_MIN);

/** The draggable, keyboard-resizable divider on the left edge of a docked right-hand panel.
 * The caller clamps: onWidth gets the wanted width and decides what to keep. */
export function DockHandle({
  label,
  width,
  min,
  max,
  onWidth,
}: {
  label: string;
  width: number;
  min: number;
  max: number;
  onWidth: (w: number) => void;
}) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={width}
      tabIndex={0}
      className="absolute inset-y-0 -left-1 w-2 cursor-col-resize touch-none hover:bg-border focus-visible:bg-ring focus-visible:outline-none"
      onPointerDown={(e) => e.currentTarget.setPointerCapture(e.pointerId)}
      onPointerMove={(e) => {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) onWidth(window.innerWidth - e.clientX);
      }}
      onKeyDown={(e) => {
        const step = e.key === "ArrowLeft" ? 24 : e.key === "ArrowRight" ? -24 : 0;
        if (!step) return;
        e.preventDefault();
        onWidth(width + step);
      }}
    />
  );
}
