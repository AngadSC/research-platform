import { upload } from "@/lib/api";
import type { Attachment } from "@/lib/api-types";

/** Google Picker, loaded from Google only when someone clicks "Link from Google Drive". */

interface PickerDoc {
  id: string;
  name: string;
}
interface PickerResponse {
  action: string;
  docs?: PickerDoc[];
}
interface PickerNs {
  Action: { PICKED: string; CANCEL: string };
  DocsView: new () => { setIncludeFolders(on: boolean): unknown };
  PickerBuilder: new () => {
    setAppId(id: string): unknown;
    setDeveloperKey(key: string): unknown;
    setOAuthToken(token: string): unknown;
    addView(view: unknown): unknown;
    setCallback(fn: (r: PickerResponse) => void): unknown;
    build(): { setVisible(on: boolean): void };
  };
}
declare global {
  interface Window {
    gapi?: { load(name: string, opts: { callback: () => void; onerror: () => void }): void };
    google?: { picker?: PickerNs };
  }
}

const SCRIPT = "https://apis.google.com/js/api.js";
let loading: Promise<void> | null = null;

export function loadPicker(): Promise<void> {
  loading ??= new Promise<void>((resolve, reject) => {
    const fail = () => {
      loading = null;
      reject(new Error("Google Drive could not be loaded. Check your connection and try again."));
    };
    const script = document.createElement("script");
    script.src = SCRIPT;
    script.async = true;
    script.onload = () =>
      window.gapi ? window.gapi.load("picker", { callback: resolve, onerror: fail }) : fail();
    script.onerror = fail;
    document.head.appendChild(script);
  });
  return loading;
}

export interface PickedFile {
  id: string;
  name: string;
}

/** Opens the Picker for one file. Resolves null when the person cancels. The token only ever
 * reaches Google's Picker; it is not stored. */
export async function pickDriveFile(opts: {
  apiKey: string;
  appId: string;
  token: string;
}): Promise<PickedFile | null> {
  await loadPicker();
  const g = window.google?.picker;
  if (!g) throw new Error("Google Drive could not be loaded. Try again.");
  return new Promise((resolve) => {
    const view = new g.DocsView();
    view.setIncludeFolders(false);
    const picker = new g.PickerBuilder();
    picker.setAppId(opts.appId);
    picker.setDeveloperKey(opts.apiKey);
    picker.setOAuthToken(opts.token);
    picker.addView(view);
    picker.setCallback((r) => {
      if (r.action === g.Action.PICKED && r.docs?.[0]) {
        resolve({ id: r.docs[0].id, name: r.docs[0].name });
      } else if (r.action === g.Action.CANCEL) resolve(null);
    });
    picker.build().setVisible(true);
  });
}

/** Posts a Drive file id to any upload endpoint that takes files (D257). Nothing is uploaded:
 * the server asks Drive itself for the file's name and link. */
export function attachFromDrive<T = Attachment>(path: string, fileId: string, extra = {}) {
  const form = new FormData();
  form.append("drive_file_id", fileId);
  for (const [k, v] of Object.entries(extra)) form.append(k, String(v));
  return upload<T>(path, form);
}
