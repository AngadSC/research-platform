import type { ExternalLink, IntegrationProvider } from "@/lib/api-types";

/** What a person reads for each connect error code the server redirects with. */
export const CONNECT_ERRORS: Record<string, string> = {
  invalid_state: "That connection attempt expired. Start again.",
  access_denied: "The connection was cancelled.",
  provider_error: "The service could not complete the connection. Try again.",
  invalid_request: "The service did not send what we needed. Try again.",
  invalid_scope: "That permission is not available.",
  unknown_provider: "That service is not available.",
  provider_not_configured: "This service is not set up for your institution yet.",
  scope_not_granted: "Allow every requested permission to connect.",
  identity_failed: "We could not confirm which account you connected. Try again.",
  unexpected_scope: "The service granted more access than we asked for. Try again.",
  other_account_connected: "Another account is already connected. Disconnect it first.",
};
export const connectError = (code: string | null) =>
  code ? (CONNECT_ERRORS[code] ?? CONNECT_ERRORS.provider_error!) : undefined;

/** Accounts that need the person to connect again. */
export const needsReconnect = (status: string | undefined) =>
  status === "expired" || status === "revoked" || status === "error";

export const STATUS_HELP: Record<string, string> = {
  active: "Connected",
  expired:
    "The service stopped accepting this connection. Reconnect to keep linked items up to date.",
  revoked: "This connection was disconnected.",
  error: "This connection has a problem on our side. Reconnect to try again.",
};

export type LinkState = {
  tone: "success" | "warning" | "destructive" | "secondary";
  label: string;
};

/** The one status shown for an external link, most serious first. */
export function linkState(link: ExternalLink): LinkState {
  if (link.unavailable_since) return { tone: "destructive", label: "No longer available" };
  if (link.changed_since_linked) return { tone: "warning", label: "Changed since linked" };
  if (link.check_blocked === "linker_access_lost")
    return {
      tone: "secondary",
      label: "Can't check: the person who linked it lost access to this project. Relink it",
    };
  if (link.linker_connection_status && link.linker_connection_status !== "active")
    return { tone: "secondary", label: "Can't check: the linker's connection is inactive" };
  return { tone: "success", label: "Up to date" };
}

export type LinkKind = ExternalLinkTarget;
type ExternalLinkTarget = IntegrationProvider["link_targets"][number];
type LinkMethod = IntegrationProvider["link_methods"][number];

/** Category groups on the Integrations page, in display order. */
export const CATEGORIES: [string, string][] = [
  ["storage", "File storage"],
  ["code", "Code"],
  ["writing", "Writing"],
  ["references", "References"],
  ["repository", "Repositories"],
  ["data_capture", "Data capture"],
  ["protocols", "Protocols"],
];

/** Connected (oauth2 and api_key) or needing no connection (link_only and public). */
export function isUsable(p: IntegrationProvider): boolean {
  if (p.auth_type === "link_only" || p.auth_type === "public") return true;
  return p.configured && p.account?.status === "active";
}

/** The Picker only exists for Google Drive and needs its public settings from the server. */
export function pickerReady(p: IntegrationProvider): boolean {
  return p.name === "google_drive" && !!p.public_config?.api_key && !!p.public_config?.app_id;
}

/** The ways this provider can link right now (a picker that cannot open is not offered). */
export function linkMethods(p: IntegrationProvider): LinkMethod[] {
  return p.link_methods.filter((m) => m !== "picker" || pickerReady(p));
}

/** Providers whose links can hang on `kind`, usable or not. */
export const offering = (providers: IntegrationProvider[] | undefined, kind: LinkKind) =>
  (providers ?? []).filter(
    (p) =>
      p.link_targets.includes(kind) &&
      linkMethods(p).length > 0 &&
      (p.auth_type !== "oauth2" || p.configured), // an OAuth service this server lacks can never be used
  );

/** Per-provider sharing note; the registry sends none, so others get the generic line. */
const SHARING: Record<string, string> = {
  google_drive: "Opening this file uses Google's own sharing settings.",
};
export const sharingNote = (provider: string, label: string) =>
  SHARING[provider] ?? `Opening this item uses ${label}'s own sharing settings.`;

/** Checks a pasted address against the provider's `url_pattern` (a Python regex that must match
 * the whole address). Returns an error message, or "" when fine or when nothing can be checked. */
export function checkPastedUrl(value: string, p: IntegrationProvider): string {
  const url = value.trim();
  if (!url) return "Paste a link.";
  try {
    if (!/^https?:$/.test(new URL(url).protocol)) throw new Error();
  } catch {
    return "Enter a full web address starting with https://";
  }
  if (!p.url_pattern) return "";
  try {
    const re = new RegExp(`^(?:${p.url_pattern.replace(/\(\?P</g, "(?<")})$`);
    return re.test(url) ? "" : `This does not look like a ${p.label} link.`;
  } catch {
    return ""; // a pattern JavaScript cannot read: the server still checks it
  }
}
