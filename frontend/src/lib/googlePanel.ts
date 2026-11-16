import { useSyncExternalStore } from "react";

/** The one Google Doc, Sheet or Slides file open beside the app (D326). It lives here, not in
 * a page, so moving to another page or project leaves it open; only its own X closes it. */
export interface GooglePanelFile {
  title: string;
  /** "Google Docs", "Google Sheets"... */
  label: string;
  src: string;
  openUrl: string;
}

let current: GooglePanelFile | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function openGooglePanel(file: GooglePanelFile) {
  current = file;
  emit();
}

export function closeGooglePanel() {
  current = null;
  emit();
}

export function useGooglePanel(): GooglePanelFile | null {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => current,
    () => null,
  );
}
