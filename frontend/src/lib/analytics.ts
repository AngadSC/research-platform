/** D380: site analytics with Umami, self-hosted on our server (docker-compose.prod.yml, served at
 * /u/ by Caddy). No cookies and no IP addresses are kept. Everything is scrubbed here before it
 * leaves the browser: page addresses lose ids, invite and email codes and every query parameter but
 * utm_*, page titles are never sent (they can hold project or document names), and actions are
 * recorded as "POST labs/:id/projects", never what was typed. Test accounts and staff are left out.
 * Only runs on the live domain. */

const WEBSITE_ID = "a9ddebdc-1c3e-4b1b-a7e2-022fffbd47b3";
const LIVE_HOST = "labbenchos.com";
const SCRIPT = "/u/s.js"; // Caddy maps it to Umami's script.js; events go to /u/api/send
const NAME_MAX = 50; // Umami's limit on event names

type Payload = Record<string, unknown> & { url?: string; referrer?: string; title?: string };
type Umami = {
  track: (name: string, data?: Record<string, unknown>) => void;
  identify: (id: string) => void;
};
declare global {
  interface Window {
    umami?: Umami;
    umamiBeforeSend?: (type: string, payload: Payload) => Payload | null;
  }
}

let excluded = false;
let pendingId = ""; // identify() can run before the tracker has loaded

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

/** A path with everything that identifies a record or carries a code replaced. */
export function pattern(path: string): string {
  let p = path.split(/[?#]/)[0] || "/";
  p = p
    .replace(/\/invite\/[^/]+/, "/invite/:token")
    .replace(/\/verify-email\/[^/]+/, "/verify-email/:key")
    .replace(/\/key\/[^/]+/, "/key/:key")
    .replace(UUID, ":id")
    .replace(/\/\d+(?=\/|$)/g, "/:n")
    .replace(/\/[A-Za-z0-9_.-]{20,}(?=\/|$)/g, "/:token");
  return p;
}

/** A full address as it may be stored: our pages as patterns plus utm_* and a plain #tab. */
export function scrubUrl(raw: string | undefined): string {
  if (!raw) return "";
  let url: URL;
  try {
    url = new URL(raw, window.location.origin);
  } catch {
    return "";
  }
  if (url.origin !== window.location.origin) return url.origin; // another site: which site only
  const keep = new URLSearchParams();
  url.searchParams.forEach((v, k) => {
    if (k.startsWith("utm_")) keep.set(k, v.slice(0, 60));
  });
  const query = keep.toString();
  const hash = /^#[a-z0-9-]{1,30}$/.test(url.hash) ? url.hash : "";
  return `${url.origin}${pattern(url.pathname)}${query ? `?${query}` : ""}${hash}`;
}

export function beforeSend(_type: string, payload: Payload): Payload | null {
  if (excluded) return null;
  const out: Payload = { ...payload, title: "" };
  if (typeof out.url === "string") out.url = scrubUrl(out.url);
  if (typeof out.referrer === "string" && out.referrer) {
    out.referrer = out.referrer.startsWith("/") ? pattern(out.referrer) : scrubUrl(out.referrer);
  }
  return out;
}

function track(name: string, data?: Record<string, unknown>) {
  if (excluded) return;
  window.umami?.track(name.slice(0, NAME_MAX), data);
}

/** Every save, create or delete the app makes, by kind only (no ids, no bodies). */
export function trackAction(method: string, path: string, status: number) {
  if (["GET", "HEAD", "OPTIONS"].includes(method)) return;
  const what = pattern(path)
    .replace(/^\/api\//, "")
    .replace(/^\/_allauth\/browser\/v1\/(auth\/)?/, "auth/")
    .replace(/\/$/, "");
  track(`${status >= 400 || status === 0 ? "FAIL " : ""}${method} ${what}`, { status });
}

const CLICKABLE =
  "button, a[href], summary, [role=menuitem], [role=menuitemradio], [role=menuitemcheckbox], [role=tab], [role=option], [role=switch], [role=checkbox], [role=radio]";

function clickLabel(el: Element): string {
  const text = (el.getAttribute("aria-label") || el.textContent || "").replace(/\s+/g, " ").trim();
  return text
    .replace(/[^\s@]+@[^\s@]+/g, "[email]")
    .replace(/\d{3,}/g, "#")
    .slice(0, 40);
}

function onClick(e: MouseEvent) {
  if (excluded || !window.umami) return;
  const target = e.target instanceof Element ? e.target : null;
  const el = target?.closest(CLICKABLE);
  if (!el || el.closest("[contenteditable=true], [data-umami-event]")) return;
  const page = pattern(window.location.pathname);
  if (el instanceof HTMLAnchorElement) {
    const href = el.getAttribute("href") ?? "";
    let to = "";
    try {
      const url = new URL(href, window.location.origin);
      to = url.origin === window.location.origin ? pattern(url.pathname) : url.hostname;
    } catch {
      return;
    }
    track(`link ${to}`, { page });
    return;
  }
  // Pages about participants may show participant codes on buttons: record that a click happened
  // there, never the label.
  const label = /participant/.test(page) ? "(participant page)" : clickLabel(el) || "(no label)";
  track(`click ${label}`, { page });
}

/** Load the tracker on the live site only. */
export function startAnalytics() {
  if (window.location.hostname !== LIVE_HOST || document.querySelector(`script[src="${SCRIPT}"]`))
    return;
  window.umamiBeforeSend = beforeSend;
  const s = document.createElement("script");
  s.defer = true;
  s.src = SCRIPT;
  s.dataset.websiteId = WEBSITE_ID;
  s.dataset.domains = LIVE_HOST;
  s.dataset.beforeSend = "umamiBeforeSend";
  s.dataset.doNotTrack = "true";
  s.dataset.performance = "true";
  s.onload = () => {
    if (pendingId && !excluded) window.umami?.identify(pendingId);
  };
  document.head.appendChild(s);
  document.addEventListener("click", onClick, true);
}

/** Tie this browser's visits to a random account id (never a name or email), so one person's
 * path through the app can be followed. Test accounts and staff are not counted at all. */
export function identifyUser(me: { id?: string; email?: string; is_staff?: boolean } | undefined) {
  if (!me?.id) return;
  if (me.is_staff) {
    try {
      localStorage.setItem("umami.disabled", "1"); // staff browsing never counts, signed in or not
    } catch {
      /* storage blocked */
    }
  }
  excluded = !!me.is_staff || (me.email ?? "").toLowerCase().endsWith("@example.test");
  if (excluded) return;
  pendingId = me.id;
  window.umami?.identify(me.id);
}
