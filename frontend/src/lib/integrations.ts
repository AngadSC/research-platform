import type { ExternalLink } from "@/lib/api-types";

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
