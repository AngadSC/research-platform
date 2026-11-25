/** Helpers for a saved item order (sidebar and top bar). Dragging items is not offered. */

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
