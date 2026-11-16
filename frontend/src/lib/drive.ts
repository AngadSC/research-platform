import { upload } from "@/lib/api";
import type { Attachment } from "@/lib/api-types";

/** Google Picker, loaded from Google only when someone clicks "Link from Google Drive". */

interface PickerDoc {
  id: string;
  name: string;
  url?: string;
}
interface PickerResponse {
  action: string;
  docs?: PickerDoc[];
}
interface DocsViewT {
  setIncludeFolders(on: boolean): DocsViewT;
  setOwnedByMe(on: boolean): DocsViewT;
  setEnableDrives(on: boolean): DocsViewT;
  setLabel?(label: string): DocsViewT;
}
interface PickerNs {
  Action: { PICKED: string; CANCEL: string };
  Feature: { MULTISELECT_ENABLED: string; SUPPORT_DRIVES: string };
  DocsView: new () => DocsViewT;
  PickerBuilder: new () => {
    enableFeature(feature: string): unknown;
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
  /** Where Google opens it, when the Picker says. */
  url?: string;
}

interface PickerOpts {
  apiKey: string;
  appId: string;
  token: string;
}

async function openPicker(opts: PickerOpts, multiple: boolean): Promise<PickedFile[]> {
  await loadPicker();
  const g = window.google?.picker;
  if (!g) throw new Error("Google Drive could not be loaded. Try again.");
  return new Promise((resolve) => {
    // Three tabs: your own Drive, files others shared with you (you need not own a file to bring
    // it in, only be able to open it), and shared drives. Picking a file is what lets this app
    // see it (drive.file), whoever owns it.
    const mine = new g.DocsView().setIncludeFolders(false).setOwnedByMe(true);
    const shared = new g.DocsView().setIncludeFolders(false).setOwnedByMe(false);
    const drives = new g.DocsView().setIncludeFolders(false).setEnableDrives(true);
    const picker = new g.PickerBuilder();
    picker.setAppId(opts.appId);
    picker.setDeveloperKey(opts.apiKey);
    picker.setOAuthToken(opts.token);
    picker.addView(mine);
    picker.addView(shared);
    picker.addView(drives);
    picker.enableFeature(g.Feature.SUPPORT_DRIVES);
    if (multiple) picker.enableFeature(g.Feature.MULTISELECT_ENABLED);
    picker.setCallback((r) => {
      if (r.action === g.Action.PICKED && r.docs?.length) {
        resolve(r.docs.map((d) => ({ id: d.id, name: d.name, url: d.url })));
      } else if (r.action === g.Action.CANCEL) resolve([]);
    });
    picker.build().setVisible(true);
  });
}

/** Opens the Picker for one file. Resolves null when the person cancels. The token only ever
 * reaches Google's Picker; it is not stored. */
export async function pickDriveFile(opts: PickerOpts): Promise<PickedFile | null> {
  return (await openPicker(opts, false))[0] ?? null;
}

/** The same Picker with several files selectable. Resolves [] when the person cancels. */
export const pickDriveFiles = (opts: PickerOpts) => openPicker(opts, true);

/** Posts a Drive file id to any upload endpoint that takes files (D257). Nothing is uploaded:
 * the server asks Drive itself for the file's name and link. */
export function attachFromDrive<T = Attachment>(path: string, fileId: string, extra = {}) {
  const form = new FormData();
  form.append("drive_file_id", fileId);
  for (const [k, v] of Object.entries(extra)) form.append(k, String(v));
  return upload<T>(path, form);
}
