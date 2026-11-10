import { useCallback, useEffect, useSyncExternalStore } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useAuth } from "@/hooks/auth";
import { api } from "@/lib/api";
import type { User } from "@/lib/api-types";
import {
  isDarkPalette,
  paletteVars,
  PALETTE_VARS,
  type CustomTheme,
  type Palette,
} from "@/lib/customTheme";

export type Theme = "light" | "dark" | "system" | `custom:${string}`;
const KEY = "theme";
const PALETTE_KEY = "theme-palette"; // the chosen custom theme's colours, for the first paint

type Prefs = { theme?: Theme; custom_themes?: CustomTheme[] };

export function getStoredTheme(): Theme {
  const v = localStorage.getItem(KEY);
  return v === "light" || v === "dark" || v?.startsWith("custom:") ? (v as Theme) : "system";
}

function storedPalette(): Palette | null {
  try {
    return JSON.parse(localStorage.getItem(PALETTE_KEY) ?? "null") as Palette | null;
  } catch {
    return null;
  }
}

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  const palette = theme.startsWith("custom:") ? storedPalette() : null;
  const dark = palette
    ? isDarkPalette(palette)
    : theme === "dark" || (theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  root.classList.toggle("dark", dark);
  const vars = palette ? paletteVars(palette) : {};
  for (const name of PALETTE_VARS) {
    const value = vars[name];
    if (value) root.style.setProperty(name, value);
    else root.style.removeProperty(name);
  }
}

const paletteOf = (theme: Theme | undefined, themes: CustomTheme[] | undefined) =>
  themes?.find((t) => `custom:${t.id}` === theme);

// One shared value, so the header toggle and the account sync always agree.
let current = getStoredTheme();
const listeners = new Set<() => void>();
const subscribe = (cb: () => void) => (listeners.add(cb), () => void listeners.delete(cb));

/** Applies a theme here only (localStorage is the fast first paint; the account is the source of truth). */
export function setThemeLocal(t: Theme, palette?: Palette) {
  localStorage.setItem(KEY, t);
  if (palette) localStorage.setItem(PALETTE_KEY, JSON.stringify(palette));
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
      const prefs = qc.getQueryData<{ preferences?: Prefs }>(["me"])?.preferences;
      setThemeLocal(t, paletteOf(t, prefs?.custom_themes));
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
  const prefs = saved as Prefs | null | undefined;
  const t = prefs?.theme;
  const palette = paletteOf(t, prefs?.custom_themes);
  useEffect(() => {
    if (t && t !== current) setThemeLocal(t, palette);
  }, [t, palette]);
}

/** Saves the list and the chosen theme together, so the account is never left on a deleted one. */
export function useSaveCustomThemes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { custom_themes: CustomTheme[]; theme: Theme }) =>
      api<User>("/api/me/", { method: "PATCH", body: { preferences: v } }),
    onSuccess: (u, v) => {
      setThemeLocal(v.theme, paletteOf(v.theme, v.custom_themes));
      qc.setQueryData(["me"], u);
    },
    onError: () => toast.error("Could not save that theme."),
  });
}
