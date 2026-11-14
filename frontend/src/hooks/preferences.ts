import { useCallback, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { Crumb } from "@/components/shared/Breadcrumbs";
import { useMe } from "@/hooks/workspace";
import { api } from "@/lib/api";
import type { User } from "@/lib/api-types";
import { addRecent, isLocalUrl, MAX_PINS, togglePin, type Pin, type Recent } from "@/lib/pins";

interface Lists {
  pins?: Pin[];
  recents?: Recent[];
  sidebar_main?: string[];
  sidebar_admin?: string[];
  delight?: "on" | "off";
}
type Me = User & { preferences?: Lists & { time_zone?: string } };
const ME = ["me"];

/** Shows the change at once, then saves it. A failed save reloads what the account really has. */
function useSaveLists() {
  const qc = useQueryClient();
  return useCallback(
    (patch: Lists) => {
      qc.setQueryData<Me>(ME, (m) => m && { ...m, preferences: { ...m.preferences, ...patch } });
      void api<User>("/api/me/", { method: "PATCH", body: { preferences: patch } }).then(
        (u) => qc.setQueryData(ME, u),
        () => qc.invalidateQueries({ queryKey: ME }),
      );
    },
    [qc],
  );
}

export function usePins() {
  const saved = (useMe().data as Me | undefined)?.preferences?.pins ?? [];
  const save = useSaveLists();
  const toggle = (pin: Pin) => {
    const pins = togglePin(saved, pin);
    if (pins) save({ pins });
    else toast.error(`You can pin up to ${MAX_PINS} pages. Unpin one first.`);
  };
  return { pins: saved.filter((p) => isLocalUrl(p.url)), toggle };
}

/** The order this person arranged the sidebar in, saved to their account so it follows them.
 * Anything they arranged in this browser before it was saved to the account is carried over once. */
export function useSidebarOrder() {
  const me = useMe().data as Me | undefined;
  const save = useSaveLists();
  const loaded = !!me;
  const mainSaved = me?.preferences?.sidebar_main;
  const adminSaved = me?.preferences?.sidebar_admin;
  useEffect(() => {
    if (!loaded || mainSaved || adminSaved) return;
    try {
      const raw = JSON.parse(localStorage.getItem(LEGACY_ORDER_KEY) ?? "null") as {
        main?: unknown;
        admin?: unknown;
      } | null;
      localStorage.removeItem(LEGACY_ORDER_KEY);
      const ok = (v: unknown): v is string[] =>
        Array.isArray(v) && v.length <= 40 && v.every((x) => typeof x === "string");
      const patch: Lists = {};
      if (ok(raw?.main)) patch.sidebar_main = raw.main;
      if (ok(raw?.admin)) patch.sidebar_admin = raw.admin;
      if (Object.keys(patch).length) save(patch);
    } catch {
      /* nothing to carry over */
    }
  }, [loaded, mainSaved, adminSaved, save]);
  return {
    main: mainSaved ?? [],
    admin: adminSaved ?? [],
    setMain: (sidebar_main: string[]) => save({ sidebar_main }),
    setAdmin: (sidebar_admin: string[]) => save({ sidebar_admin }),
    reset: () => save({ sidebar_main: [], sidebar_admin: [] }),
  };
}
const LEGACY_ORDER_KEY = "sidebar-order";

/** The small animations (a task checking off, a confetti-free "all caught up"). On unless the
 * person turned them off in Settings or asked their device for less motion. */
export function useDelight(): boolean {
  const pref = (useMe().data as Me | undefined)?.preferences?.delight;
  const reduced =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  return pref !== "off" && !reduced;
}

export function useRecents(): Recent[] {
  const saved = (useMe().data as Me | undefined)?.preferences?.recents ?? [];
  return saved.filter((r) => isLocalUrl(r.url));
}

/** Records the project, document or record the page belongs to, once its name has loaded. */
export function useTrackRecent(crumbs: Crumb[]) {
  const qc = useQueryClient();
  const save = useSaveLists();
  const loaded = !!useMe().data;
  const item = crumbs.filter((c) => c.kind).at(-1);
  const ready = loaded && item && !item.pending;
  const url = ready ? item.to : undefined;
  const label = item?.label;
  const kind = item?.kind;

  useEffect(() => {
    if (!url || !label || !kind) return;
    const recents = qc.getQueryData<Me>(ME)?.preferences?.recents ?? [];
    const next = addRecent(recents, { url, label, kind, at: new Date().toISOString() });
    if (next) save({ recents: next });
  }, [qc, save, url, label, kind]);
}

/** D291: tells the account which time zone this browser is in, so the server's "today" (and the
 * dates Claude sees) match this person's. Silent: a refused or failed save is simply dropped. */
export function useSyncTimeZone() {
  const qc = useQueryClient();
  const me = useMe().data as Me | undefined;
  const saved = me?.preferences?.time_zone;
  const loaded = !!me;
  const sent = useRef("");
  useEffect(() => {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    // The server stores a current name for an old one (Asia/Calcutta), so `saved` can differ
    // from `zone` for good: send each zone once.
    if (!loaded || !zone || zone === saved || zone === sent.current) return;
    sent.current = zone;
    void api<User>("/api/me/", {
      method: "PATCH",
      body: { preferences: { time_zone: zone } },
    }).then(
      (u) => qc.setQueryData(ME, u),
      () => {},
    );
  }, [qc, loaded, saved]);
}
