import { useCallback, useEffect, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/auth";
import { api } from "@/lib/api";
import type { User } from "@/lib/api-types";

export type Theme = "light" | "dark" | "system";
const KEY = "theme";

export function getStoredTheme(): Theme {
  const v = localStorage.getItem(KEY);
  return v === "light" || v === "dark" ? v : "system";
}

export function applyTheme(theme: Theme) {
  const dark =
    theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

// One shared value, so the header toggle and the account sync always agree.
let current = getStoredTheme();
const listeners = new Set<() => void>();
const subscribe = (cb: () => void) => (listeners.add(cb), () => void listeners.delete(cb));

/** Applies a theme here only (localStorage is the fast first paint; the account is the source of truth). */
export function setThemeLocal(t: Theme) {
  localStorage.setItem(KEY, t);
  current = t;
  applyTheme(t);
  listeners.forEach((l) => l());
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, () => current);
  const { isAuthenticated } = useAuth();
  const qc = useQueryClient();

  const setTheme = useCallback(
    (t: Theme) => {
      setThemeLocal(t);
      if (!isAuthenticated) return;
      api<User>("/api/me/", { method: "PATCH", body: { preferences: { theme: t } } }).then(
        (u) => qc.setQueryData(["me"], u),
        () => undefined, // saved on this device either way
      );
    },
    [isAuthenticated, qc],
  );

  useEffect(() => {
    if (theme !== "system") return;
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  return { theme, setTheme };
}

/** Adopts the theme saved on the account when it differs from this device's. Mount once, signed in. */
export function useAccountTheme(saved: unknown) {
  const t = (saved as { theme?: Theme } | null | undefined)?.theme;
  useEffect(() => {
    if (t && t !== current) setThemeLocal(t);
  }, [t]);
}
