export type FieldErrors = Record<string, string>;

const MESSAGES: Record<number, string> = {
  401: "Please sign in to continue.",
  403: "You don't have permission to do that.",
  404: "We couldn't find that. It may have been removed.",
  409: "That conflicts with something that already exists or has just changed. Refresh and try again.",
};
const SERVER_MESSAGE = "Something went wrong on our side. Please try again in a moment.";

export class ApiError extends Error {
  status: number;
  fieldErrors: FieldErrors;
  body: unknown;
  constructor(
    status: number,
    message: string,
    fieldErrors: FieldErrors = {},
    body: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.body = body;
  }
}

const first = (v: unknown): string | undefined =>
  Array.isArray(v) ? (v[0] as string | undefined) : typeof v === "string" ? v : undefined;

/** Turns DRF ({detail} / {field: [msg]}) and allauth ({errors: [{message, param}]}) bodies into an ApiError. */
export function toApiError(status: number, body: unknown): ApiError {
  const fieldErrors: FieldErrors = {};
  let message: string | undefined;
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    if (Array.isArray(b.errors)) {
      for (const e of b.errors as { message?: string; param?: string }[]) {
        if (!e.message) continue;
        if (e.param) fieldErrors[e.param] ??= e.message;
        else message ??= e.message;
      }
    } else {
      for (const [k, v] of Object.entries(b)) {
        const m = first(v);
        if (k === "detail" || k === "non_field_errors") message ??= m;
        else if (m) fieldErrors[k] = m;
      }
    }
  }
  const general = status >= 500 ? SERVER_MESSAGE : status === 400 ? undefined : MESSAGES[status];
  // 4xx other than 400: our friendly text wins unless the server gave a specific reason (403 invite mismatch etc.).
  const text =
    status === 403 || status === 409 ? (message ?? general) : status === 400 ? message : general;
  const fallback = Object.values(fieldErrors)[0] ?? "Something went wrong. Please try again.";
  return new ApiError(status, text ?? fallback, fieldErrors, body);
}

export function getCookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

export const SESSION_URL = "/_allauth/browser/v1/auth/session";
const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

interface Options {
  method?: string;
  body?: unknown;
}

/** Low-level call: never throws on HTTP status (allauth uses 401 for pending flows). */
export async function rawRequest(
  path: string,
  { method = "GET", body }: Options = {},
): Promise<{ status: number; body: unknown }> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (!SAFE.has(method)) {
    // The CSRF cookie is only set after a first GET.
    if (!getCookie("csrftoken")) await fetch(SESSION_URL, { headers });
    headers["X-CSRFToken"] = getCookie("csrftoken") ?? "";
  }
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "We couldn't reach the server. Check your connection and try again.");
  }
  const text = await res.text();
  try {
    return { status: res.status, body: text ? JSON.parse(text) : null };
  } catch {
    return { status: res.status, body: null };
  }
}

/** JSON call that throws ApiError for any non-2xx. */
export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const { status, body } = await rawRequest(path, opts);
  if (status < 200 || status >= 300) throw toApiError(status, body);
  return body as T;
}
