/** Pinned and recent pages, kept in `preferences` (validated again in core/serializers.py). */
export interface Pin {
  url: string;
  label: string;
}
export type RecentKind = "project" | "document" | "record" | "approval";
export interface Recent extends Pin {
  kind: RecentKind;
  at: string;
}

export const MAX_PINS = 20;
export const MAX_RECENTS = 12;
const MAX_LABEL = 300;

/** A path on this site. "/\x" and "/<tab>/x" count as "//x" to a browser, so they are out too. */
export const isLocalUrl = (url: string) => /^\/(?![/\\])[^\s\\]*$/.test(url);

/** The list with `pin` added or removed; null when it cannot be added. */
export function togglePin(pins: Pin[], pin: Pin): Pin[] | null {
  if (pins.some((p) => p.url === pin.url)) return pins.filter((p) => p.url !== pin.url);
  if (pins.length >= MAX_PINS || !isLocalUrl(pin.url)) return null;
  return [...pins, { url: pin.url, label: pin.label.slice(0, MAX_LABEL) }];
}

/** The list with `item` on top, or null when there is nothing to save. */
export function addRecent(recents: Recent[], item: Recent): Recent[] | null {
  const label = item.label.slice(0, MAX_LABEL);
  if (!isLocalUrl(item.url)) return null;
  if (recents[0]?.url === item.url && recents[0]?.label === label) return null;
  return [{ ...item, label }, ...recents.filter((r) => r.url !== item.url)].slice(0, MAX_RECENTS);
}
