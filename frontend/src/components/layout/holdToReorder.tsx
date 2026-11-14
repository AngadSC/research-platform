import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";

/** How long a press must last before it turns into a drag, so a plain click still navigates. */
const HOLD_MS = 280;
/** Moving this far before the hold ends is a scroll or a click, not the start of a drag. */
const SLOP = 6;
const SETTLE_MS = 180;

export function moveId(ids: string[], id: string, to: number): string[] {
  const next = ids.filter((x) => x !== id);
  next.splice(Math.max(0, Math.min(to, next.length)), 0, id);
  return next;
}

/** The saved order applied to what exists now: unknown ids go last, in their given order. */
export function applyOrder<T>(items: T[], idOf: (t: T) => string, saved: string[]): T[] {
  const rank = new Map(saved.map((id, i) => [id, i]));
  return items
    .map((item, i) => ({ item, i, r: rank.get(idOf(item)) ?? saved.length + i }))
    .sort((a, b) => a.r - b.r)
    .map((x) => x.item);
}

interface Drag {
  id: string;
  from: number;
  to: number;
  dy: number;
  settling: boolean;
}

/**
 * Press and hold a row, then drag it up or down to move it; the others slide out of the way, and it
 * settles into place on release. Alt+Arrow keys do the same from the keyboard. A drag never
 * becomes a click. `ids` is the current order; `onReorder` gets the new one.
 */
export function useHoldToReorder(ids: string[], onReorder: (next: string[]) => void) {
  const [drag, setDrag] = useState<Drag | null>(null);
  const [lifted, setLifted] = useState<string | null>(null);
  const rects = useRef<{ top: number; height: number }[]>([]);
  const nodes = useRef(new Map<string, HTMLElement>());
  const hold = useRef<{ timer: number; x: number; y: number; id: string; pointer: number } | null>(
    null,
  );
  const live = useRef<{ startY: number; id: string; from: number } | null>(null);
  const dropped = useRef(false);
  const idsRef = useRef(ids);
  useEffect(() => {
    idsRef.current = ids;
  });

  const clearHold = () => {
    if (hold.current) window.clearTimeout(hold.current.timer);
    hold.current = null;
  };
  useEffect(() => clearHold, []);

  const targetIndex = useCallback((from: number, dy: number) => {
    const r = rects.current;
    const centre = r[from]!.top + r[from]!.height / 2 + dy;
    let to = 0;
    r.forEach((m, i) => {
      if (i !== from && m.top + m.height / 2 < centre) to++;
    });
    return to;
  }, []);

  const finish = useCallback(() => {
    const d = live.current;
    live.current = null;
    setLifted(null);
    setDrag((cur) => {
      if (!cur || !d) return null;
      const r = rects.current;
      const { from, to } = cur;
      const gap = r.length > 1 ? Math.max(0, r[1]!.top - (r[0]!.top + r[0]!.height)) : 0;
      let offset = 0;
      if (to > from) for (let i = from + 1; i <= to; i++) offset += r[i]!.height + gap;
      else for (let i = to; i < from; i++) offset -= r[i]!.height + gap;
      window.setTimeout(() => {
        setDrag(null);
        if (to !== from) onReorder(moveId(idsRef.current, cur.id, to));
      }, SETTLE_MS);
      return { ...cur, dy: offset, settling: true };
    });
  }, [onReorder]);

  const begin = (id: string, pointer: number, clientY: number, el: HTMLElement) => {
    rects.current = idsRef.current.map((x) => {
      const b = nodes.current.get(x)?.getBoundingClientRect();
      return { top: b?.top ?? 0, height: b?.height ?? 0 };
    });
    const from = idsRef.current.indexOf(id);
    live.current = { startY: clientY, id, from };
    dropped.current = true; // swallow the click that follows this gesture
    setLifted(id);
    setDrag({ id, from, to: from, dy: 0, settling: false });
    try {
      el.setPointerCapture(pointer);
    } catch {
      /* the element may already be gone; the window listeners below still work */
    }
  };

  useEffect(() => {
    if (!lifted) return;
    const move = (e: PointerEvent) => {
      const d = live.current;
      if (!d) return;
      const dy = e.clientY - d.startY;
      setDrag((cur) => cur && { ...cur, dy, to: targetIndex(d.from, dy) });
    };
    const up = () => finish();
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    };
  }, [lifted, finish, targetIndex]);

  /** Props for the element wrapping one row. */
  const rowProps = (id: string) => ({
    ref: (el: HTMLElement | null) => {
      if (el) nodes.current.set(id, el);
      else nodes.current.delete(id);
    },
    onPointerDown: (e: React.PointerEvent<HTMLElement>) => {
      if (e.button !== 0 || e.pointerType === "touch" || drag) return;
      const el = e.currentTarget;
      const { clientX: x, clientY: y, pointerId } = e;
      clearHold();
      hold.current = {
        x,
        y,
        id,
        pointer: pointerId,
        timer: window.setTimeout(() => {
          hold.current = null;
          begin(id, pointerId, y, el);
        }, HOLD_MS),
      };
    },
    onPointerMove: (e: React.PointerEvent<HTMLElement>) => {
      const h = hold.current;
      if (h && Math.hypot(e.clientX - h.x, e.clientY - h.y) > SLOP) clearHold();
    },
    onPointerUp: clearHold,
    onPointerCancel: clearHold,
    onDragStart: (e: React.DragEvent) => e.preventDefault(), // links drag as images otherwise
    onClickCapture: (e: React.MouseEvent) => {
      if (dropped.current) {
        dropped.current = false;
        e.preventDefault();
        e.stopPropagation();
      }
    },
    onKeyDown: (e: React.KeyboardEvent<HTMLElement>) => {
      if (!e.altKey || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
      const at = ids.indexOf(id);
      const to = at + (e.key === "ArrowUp" ? -1 : 1);
      if (to < 0 || to >= ids.length) return;
      e.preventDefault();
      onReorder(moveId(ids, id, to));
      // Keep the focus on the moved row once React has re-ordered it.
      requestAnimationFrame(() =>
        nodes.current.get(id)?.querySelector<HTMLElement>("a,button")?.focus(),
      );
    },
  });

  /** Inline style for one row: the lifted one follows the pointer, the rest slide aside. */
  const rowStyle = (id: string): CSSProperties | undefined => {
    if (!drag) return undefined;
    const i = ids.indexOf(id);
    const r = rects.current;
    if (id === drag.id)
      return {
        transform: `translateY(${drag.dy}px) scale(${drag.settling ? 1 : 1.03})`,
        transition: drag.settling ? `transform ${SETTLE_MS}ms ease-out` : "none",
        zIndex: 20,
        position: "relative",
        boxShadow: drag.settling ? "none" : "0 6px 18px rgb(0 0 0 / 0.25)",
        cursor: "grabbing",
      };
    const h = r[drag.from]?.height ?? 0;
    const gap = r.length > 1 ? Math.max(0, r[1]!.top - (r[0]!.top + r[0]!.height)) : 0;
    let shift = 0;
    if (drag.from < i && i <= drag.to) shift = -(h + gap);
    else if (drag.to <= i && i < drag.from) shift = h + gap;
    return { transform: `translateY(${shift}px)`, transition: `transform ${SETTLE_MS}ms ease-out` };
  };

  return { rowProps, rowStyle, dragging: !!drag };
}

/** Wraps rows in the order given. Kept as a component so callers only list their rows. */
export function ReorderRow({
  id,
  reorder,
  children,
}: {
  id: string;
  reorder: ReturnType<typeof useHoldToReorder>;
  children: ReactNode;
}) {
  return (
    <div
      {...reorder.rowProps(id)}
      style={reorder.rowStyle(id)}
      className={reorder.dragging ? "min-w-0 rounded-md bg-sidebar select-none" : "min-w-0"}
    >
      {children}
    </div>
  );
}
