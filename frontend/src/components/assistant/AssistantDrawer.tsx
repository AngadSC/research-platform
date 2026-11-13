import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useMatches } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  Check,
  Loader2,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { ApprovalDialog } from "@/components/assistant/ApprovalDialog";
import { FormError } from "@/components/shared/FormError";
import {
  announcePanel,
  DockHandle,
  PANEL_OPENED,
  type PanelName,
} from "@/components/shared/DockHandle";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  conversationKey,
  useAssistantConfig,
  useConversation,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  type AssistantConfig,
  type Provider,
  type TimelineItem,
} from "@/hooks/assistant";
import { useAiGrants } from "@/hooks/ai";
import { ClaudeSteps } from "@/pages/settings/AiAccessSections";
import { useProject } from "@/hooks/projects";
import { useLabs } from "@/hooks/workspace";
import {
  ASSISTANT_PREFILL,
  estimateCost,
  formatCost,
  reduceLive,
  SAVED_NOTICES,
  streamPost,
  tokensIn,
  type Live,
} from "@/lib/assistant";
import { MOD_KEY } from "@/lib/constants";
import { MessageText } from "@/lib/markdown";
import { NativeSelect } from "@/pages/admin/common";

function ToolStatus({ status }: { status: string }) {
  if (status === "running") return <Loader2 className="size-3.5 animate-spin" aria-hidden />;
  if (status === "done") return <Check className="size-3.5 text-success" aria-hidden />;
  if (status === "declined") return <Ban className="size-3.5 text-muted-foreground" aria-hidden />;
  if (status === "pending") return <span className="text-xs">waiting for you</span>;
  return <X className="size-3.5 text-destructive" aria-hidden />;
}

const STATUS_WORD: Record<string, string> = {
  running: "working",
  done: "done",
  error: "failed",
  declined: "declined",
  pending: "waiting for approval",
};

function ToolRow({ label, status }: { label: string; status: string }) {
  return (
    <li className="flex items-center gap-2 text-xs text-muted-foreground">
      <ToolStatus status={status} />
      <span>
        {label} <span className="sr-only">({STATUS_WORD[status] ?? status})</span>
      </span>
    </li>
  );
}

/** VISION C1: one step Claude ran in the code sandbox, collapsed, with the files it made. */
function CodeRow({ item }: { item: TimelineItem }) {
  const status = item.status ?? "done";
  const pre =
    "max-h-60 overflow-auto whitespace-pre-wrap break-words rounded bg-muted p-2 font-mono";
  return (
    <div className="grid gap-1 text-xs text-muted-foreground">
      <details>
        <summary className="flex cursor-pointer items-center gap-2 rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
          <ToolStatus status={status} />
          <span>
            {item.title ?? "Ran code"}{" "}
            <span className="sr-only">({STATUS_WORD[status] ?? status}, show the code)</span>
          </span>
        </summary>
        <div className="mt-1 grid gap-1 pl-5">
          <pre className={`${pre} text-foreground`}>{item.code}</pre>
          {item.output && (
            <>
              <p>Output</p>
              <pre className={pre}>{item.output}</pre>
            </>
          )}
        </div>
      </details>
      {item.files && item.files.length > 0 && (
        <ul className="grid gap-0.5 pl-5" aria-label="Files it made">
          {item.files.map((f, i) => (
            <li key={i}>
              {f.url ? (
                <>
                  <Link className="underline underline-offset-4" to={f.url}>
                    {f.name}
                  </Link>
                  {f.analysis_url && (
                    <>
                      {" · "}
                      <Link className="underline underline-offset-4" to={f.analysis_url}>
                        Analysis
                      </Link>
                    </>
                  )}
                </>
              ) : (
                `${f.name} (not saved yet)`
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Notice({
  code,
  refusal,
  message,
}: {
  code?: string;
  refusal?: unknown;
  message?: string;
}) {
  const r = refusal as { category?: string | null; explanation?: string | null } | null;
  const text =
    code === "refusal"
      ? `The model declined to answer${r?.category ? ` (${r.category})` : ""}.${
          r?.explanation ? ` ${r.explanation}` : ""
        } Try rephrasing.`
      : (message ?? "");
  return (
    <p role="status" className="rounded-md bg-muted px-3 py-2 text-sm">
      {text}
    </p>
  );
}

function UsageLine({ item, config }: { item: TimelineItem; config?: AssistantConfig }) {
  const u = item.usage ?? {};
  const price = config?.providers.flatMap((p) => p.models).find((m) => m.id === item.model);
  const cost = estimateCost(u, price);
  return (
    <p className="mt-1 text-xs text-muted-foreground">
      {item.model} · {tokensIn(u).toLocaleString()} tokens in ·{" "}
      {(u.output_tokens ?? 0).toLocaleString()} out{cost !== null ? ` · ${formatCost(cost)}` : ""}
      {item.fallback ? " · answered by a fallback model after a refusal" : ""}
    </p>
  );
}

function Item({ item, config }: { item: TimelineItem; config?: AssistantConfig }) {
  if (item.kind === "user")
    return (
      <div className="ml-auto max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
        {item.text}
      </div>
    );
  if (item.kind === "tool")
    return <ToolRow label={item.title ?? item.name ?? "Tool"} status={item.status ?? "done"} />;
  if (item.kind === "code") return <CodeRow item={item} />;
  if (item.kind === "usage")
    return (
      <p className="text-xs text-muted-foreground">
        {tokensIn(item.usage ?? {}).toLocaleString()} tokens in ·{" "}
        {(item.usage?.output_tokens ?? 0).toLocaleString()} out
      </p>
    );
  return (
    <div className="grid gap-1">
      {item.text && (
        <div className="max-w-[95%] text-sm [&_p]:mb-1">
          <MessageText text={item.text} ownLinksOnly />
        </div>
      )}
      {item.refusal && <Notice code="refusal" refusal={item.refusal} />}
      {item.truncated && (
        <Notice message="The answer was cut off because it hit the length limit." />
      )}
      <UsageLine item={item} config={config} />
    </div>
  );
}

export function Setup({
  config,
  onOpenSettings,
}: {
  config: AssistantConfig;
  /** The drawer closes itself so the Settings page behind it can be seen. */
  onOpenSettings?: () => void;
}) {
  if (!config.can_use)
    return (
      <p role="alert" className="rounded-md border p-3 text-sm">
        {config.ai_policy === "off"
          ? "AI assistants are turned off for this lab."
          : "This lab allows AI apps over MCP only; the in-app assistant is turned off."}{" "}
        A PI or lab admin can change this in Lab details, on the AI tab.
      </p>
    );
  return (
    <div className="grid gap-3">
      <ClaudeOption />
      <div className="grid justify-items-start gap-1 text-sm">
        <p className="text-muted-foreground">
          Or add your own API key to use the assistant here. It is billed to your account with the
          provider.
        </p>
        <Link
          to="/settings#ai"
          className="font-medium underline underline-offset-2"
          onClick={onOpenSettings}
        >
          Set up a key
        </Link>
        {!config.lab_key && (
          <p className="text-xs text-muted-foreground">
            Or ask your lab admin to add a lab key, so everyone can use the assistant.
          </p>
        )}
      </div>
    </div>
  );
}

/** A popup docked to the right 40% of the screen, where claude.ai can sit beside this page. */
function claudeWindowFeatures() {
  const s = window.screen as Screen & { availLeft?: number; availTop?: number };
  const width = Math.round(s.availWidth * 0.4);
  const left = (s.availLeft ?? 0) + s.availWidth - width;
  return `popup=yes,width=${width},height=${s.availHeight},left=${left},top=${s.availTop ?? 0}`;
}

/** No key: steer people to Claude through our connector instead. claude.ai cannot be framed, so
 * it opens in a window beside this page (a plain new tab if the popup is blocked). */
function ClaudeOption() {
  const grants = useAiGrants();
  const connected = !!grants.data?.some(
    (g) => g.kind === "oauth" && !g.revoked_at && /claude/i.test(g.client_name),
  );
  return (
    <div className="grid justify-items-start gap-2 rounded-md border p-3 text-sm">
      <h3 className="font-medium">Use Claude with this lab</h3>
      {connected ? (
        <p className="text-muted-foreground">Claude is connected to your labs.</p>
      ) : (
        <ClaudeSteps />
      )}
      <Button asChild size="sm">
        <a
          href="https://claude.ai/new"
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => {
            if (window.open("https://claude.ai/new", "labbenchos-claude", claudeWindowFeatures()))
              e.preventDefault(); // a popup opened; otherwise the link opens a new tab
          }}
        >
          Open Claude beside this page
        </a>
      </Button>
      <p className="text-xs text-muted-foreground">
        In Chrome you can also drag this tab next to Claude for split view.
      </p>
    </div>
  );
}

function AssistantPanel({
  labId,
  projectId,
  page,
  initialText = "",
  prefill,
  docked = false,
  onClose,
  onCollapse,
}: {
  labId: string;
  projectId?: string;
  /** The open page as kind and ids only; sent with each message. */
  page?: PageContext;
  initialText?: string;
  /** Docked: the panel stays mounted, so a new prefill replaces the box. */
  prefill?: { text: string; n: number };
  docked?: boolean;
  onClose: () => void;
  onCollapse?: () => void;
}) {
  const qc = useQueryClient();
  const config = useAssistantConfig(labId, true);
  const convs = useConversations(labId, true);
  const lab = useLabs().data?.find((l) => l.id === labId);
  const project = useProject(labId, projectId).data;
  const [convId, setConvId] = useState<string | null>(null);
  const conv = useConversation(labId, convId);
  const create = useCreateConversation(labId);
  const remove = useDeleteConversation(labId);
  const [provider, setProvider] = useState<Provider | null>(null);
  const [model, setModel] = useState("");
  const [text, setText] = useState(initialText);
  const [seenPrefill, setSeenPrefill] = useState(prefill);
  if (prefill !== seenPrefill) {
    setSeenPrefill(prefill);
    if (prefill?.text) setText(prefill.text);
  }
  const [live, setLive] = useState<Live | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [dismissedFor, setDismissedFor] = useState("");
  const abort = useRef<AbortController | null>(null);
  const [lastSent, setLastSent] = useState("");
  const end = useRef<HTMLDivElement>(null);

  const cfg = config.data;
  const usable = cfg?.can_use ? cfg.providers.filter((p) => p.has_key) : [];
  const chosen = usable.find((p) => p.provider === provider) ?? usable[0];
  const pending = useMemo(() => conv.data?.pending ?? [], [conv.data]);
  const pendingKey = pending.map((p) => p.id).join(",");
  const dismissed = dismissedFor === pendingKey; // a new set of waiting actions asks again

  useEffect(() => () => abort.current?.abort(), []); // closing the drawer stops the answer
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [conv.data?.items.length, live?.text, live?.tools.length]);

  async function run(path: string, body: unknown, id: string, user: string) {
    const ctrl = new AbortController();
    abort.current = ctrl;
    setLive({ user, text: "", tools: [], notice: null, error: null });
    setStreaming(true);
    try {
      await streamPost(path, body, (e) => setLive((l) => (l ? reduceLive(l, e) : l)), ctrl.signal);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Something went wrong.";
      setLive((l) => (l ? { ...l, error: { message, retryable: false } } : l));
    } finally {
      setStreaming(false);
      await qc.invalidateQueries({ queryKey: conversationKey(labId, id) });
      void qc.invalidateQueries({ queryKey: ["assistant", labId, "conversations"] });
      // the saved conversation now shows the text, tool rows, refusals and cut-off answers; keep
      // only what is not saved
      setLive((l) =>
        l
          ? {
              ...l,
              user: "",
              text: "",
              tools: [],
              notice: SAVED_NOTICES.has(String(l.notice?.code)) ? null : l.notice,
            }
          : l,
      );
    }
  }

  async function send(message: string) {
    const msg = message.trim();
    if (!msg || streaming || !chosen) return;
    setText("");
    setLastSent(msg);
    let id = convId;
    if (!id) {
      try {
        const c = await create.mutateAsync({
          provider: chosen.provider,
          model: model || chosen.default_model,
          ...(projectId ? { project: projectId } : {}),
        });
        id = c.id;
        setConvId(id);
      } catch (e) {
        const message = e instanceof Error ? e.message : "Could not start a chat.";
        setLive({
          user: "",
          text: "",
          tools: [],
          notice: null,
          error: { message, retryable: false },
        });
        return;
      }
    }
    await run(
      `/api/labs/${labId}/assistant/conversations/${id}/messages/`,
      { text: msg, ...(page ? { page } : {}) },
      id,
      msg,
    );
  }

  async function decide(approve: boolean) {
    if (!convId) return;
    const decisions = Object.fromEntries(pending.map((p) => [p.id, approve]));
    await run(
      `/api/labs/${labId}/assistant/conversations/${convId}/approvals/`,
      { decisions },
      convId,
      "",
    );
  }

  function newChat() {
    abort.current?.abort();
    setConvId(null);
    setLive(null);
  }

  const scope = project?.name ?? (conv.data?.project ? "this project" : null);
  const items = conv.data?.items ?? [];
  const atStart = !convId;

  return (
    <>
      <div className={`flex items-start justify-between gap-2 ${docked ? "" : "pr-8"}`}>
        <div>
          {docked ? (
            <p className="text-base font-semibold">Assistant</p>
          ) : (
            <SheetTitle className="text-base">Assistant</SheetTitle>
          )}
          <p className="text-xs text-muted-foreground">
            {lab?.name ?? "This lab"}
            {scope ? ` · ${scope}` : ""}. It sees only what you can see.
          </p>
        </div>
        <div className="flex gap-1">
          <Button variant="ghost" size="icon" aria-label="New chat" onClick={newChat}>
            <Plus aria-hidden />
          </Button>
          {convId && (
            <Button
              variant="ghost"
              size="icon"
              aria-label="Delete this chat"
              onClick={() => {
                if (!window.confirm("Delete this chat and its saved messages?")) return;
                remove.mutate(convId, { onSuccess: newChat });
              }}
            >
              <Trash2 aria-hidden />
            </Button>
          )}
          {docked && (
            <>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Collapse the assistant to a side strip"
                onClick={onCollapse}
              >
                <PanelRightClose aria-hidden />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Close the assistant"
                title={`Close (${MOD_KEY} .)`}
                onClick={onClose}
              >
                <X aria-hidden />
              </Button>
            </>
          )}
        </div>
      </div>
      <p role="note" className="rounded-md bg-muted px-3 py-2 text-xs">
        {cfg?.privacy_notice ??
          "Content from records you can see is sent to the AI provider under your own API key. Do not paste participant identifiers."}
      </p>

      {config.isLoading && (
        <div aria-busy="true" aria-label="Loading assistant" className="grid gap-2">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-16 w-full" />
        </div>
      )}
      {cfg && usable.length === 0 && (
        <Setup config={cfg} onOpenSettings={docked ? undefined : onClose} />
      )}
      {cfg && usable.length > 0 && (
        <>
          {(convs.data ?? []).length > 0 && (
            <NativeSelect
              aria-label="Conversation"
              value={convId ?? ""}
              onChange={(e) => {
                setConvId(e.target.value || null);
                setLive(null);
              }}
            >
              <option value="">New chat</option>
              {(convs.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title || "Untitled"} ({c.model})
                </option>
              ))}
            </NativeSelect>
          )}
          {atStart && (
            <div className="grid grid-cols-2 gap-2">
              <NativeSelect
                aria-label="Provider"
                value={chosen?.provider}
                onChange={(e) => {
                  setProvider(e.target.value as Provider);
                  setModel("");
                }}
              >
                {usable.map((p) => (
                  <option key={p.provider} value={p.provider}>
                    {p.label}
                  </option>
                ))}
              </NativeSelect>
              <NativeSelect
                aria-label="Model"
                value={model || chosen?.default_model}
                onChange={(e) => setModel(e.target.value)}
              >
                {chosen?.models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </NativeSelect>
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto" aria-live="polite" aria-label="Messages">
            <div className="grid gap-3 py-1">
              {atStart && !live && (
                <p className="text-sm text-muted-foreground">
                  Ask about your projects, tasks, documents, approvals or funding. I will cite the
                  records I use.
                </p>
              )}
              {items.map((it) => (
                <Item key={it.id} item={it} config={cfg} />
              ))}
              {live?.user && (
                <div className="ml-auto max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
                  {live.user}
                </div>
              )}
              {live && live.tools.length > 0 && (
                <ul className="grid gap-1" aria-label="Working">
                  {live.tools.map((t, i) => (
                    <ToolRow key={i} label={t.label} status={t.status} />
                  ))}
                </ul>
              )}
              {live?.text && (
                <div className="max-w-[95%] text-sm [&_p]:mb-1">
                  <MessageText text={live.text} ownLinksOnly />
                </div>
              )}
              {streaming && !live?.text && (
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" aria-hidden /> Thinking…
                </p>
              )}
              {live?.notice && !streaming && (
                <Notice
                  code={String(live.notice.code)}
                  refusal={live.notice.refusal}
                  message={String(live.notice.message ?? "")}
                />
              )}
              {live?.error && (
                <div className="grid gap-2">
                  <FormError message={live.error.message} />
                  {live.error.retryable && lastSent && !streaming && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-fit"
                      onClick={() => void send(lastSent)}
                    >
                      Try again
                    </Button>
                  )}
                </div>
              )}
              {pending.length > 0 && !streaming && dismissed && (
                <div className="flex items-center justify-between rounded-md border p-2 text-sm">
                  <span>
                    {pending.length} action{pending.length > 1 ? "s" : ""} waiting for your
                    approval.
                  </span>
                  <Button size="sm" onClick={() => setDismissedFor("")}>
                    Review
                  </Button>
                </div>
              )}
              <div ref={end} />
            </div>
          </div>

          <form
            className="grid gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void send(text);
            }}
          >
            <Textarea
              aria-label="Message"
              placeholder="Ask the assistant…"
              rows={2}
              value={text}
              maxLength={8000}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(text);
                }
              }}
            />
            <div className="flex justify-end gap-2">
              {streaming && (
                <Button type="button" variant="outline" onClick={() => abort.current?.abort()}>
                  Stop
                </Button>
              )}
              <Button type="submit" disabled={streaming || !text.trim()}>
                Send
              </Button>
            </div>
          </form>
        </>
      )}

      <ApprovalDialog
        calls={pending}
        open={!streaming && !dismissed}
        busy={streaming}
        onApprove={() => void decide(true)}
        onDecline={() => void decide(false)}
        onClose={() => setDismissedFor(pendingKey)}
      />
    </>
  );
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
type PageContext = { kind: "project" | "document" | "dataset"; id: string; project?: string };

/** What the person has open, as a kind and ids only (never page text). */
function pageContext(params: Record<string, string | undefined>): PageContext | undefined {
  const { projectId: project, documentId, kind, id } = params;
  const ok = (v?: string): v is string => !!v && UUID.test(v);
  const inProject = ok(project) ? { project } : {};
  if (ok(documentId)) return { kind: "document", id: documentId, ...inProject };
  if (kind === "datasets" && ok(id)) return { kind: "dataset", id, ...inProject };
  return ok(project) ? { kind: "project", id: project } : undefined;
}

const DOCK_KEY = "assistant-dock";
const MIN_W = 320;
const MAX_W = 640;
const STRIP_W = 40;
type Dock = { mode: "open" | "strip" | "closed"; width: number };
const clampWidth = (w: number) =>
  Math.round(Math.min(Math.max(w, MIN_W), Math.max(MIN_W, Math.min(MAX_W, window.innerWidth / 2))));

function readDock(): Dock {
  try {
    const d = JSON.parse(localStorage.getItem(DOCK_KEY) ?? "{}") as Partial<Dock>;
    return {
      mode: d.mode === "open" || d.mode === "strip" ? d.mode : "closed",
      width: clampWidth(typeof d.width === "number" ? d.width : 384),
    };
  } catch {
    return { mode: "closed", width: 384 }; // storage is blocked: start closed
  }
}

const WIDE = "(min-width: 768px)";

/** True from 768px up, where the assistant docks instead of covering the page. */
function useWide() {
  const [wide, setWide] = useState(() => !!window.matchMedia?.(WIDE).matches);
  useEffect(() => {
    const mq = window.matchMedia?.(WIDE);
    if (!mq) return;
    const on = () => setWide(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return wide;
}

/** The header button and the assistant. From 768px up it is a panel docked on the right that
 * pushes the page over and stays open across pages (D272); on phones it is a full-screen sheet
 * (D190). Scoped to the current lab, and to the current project when the page is inside one. */
export function AssistantDrawer({ labId }: { labId: string }) {
  const wide = useWide();
  const [open, setOpen] = useState(false); // the phone sheet
  const [dock, setDock] = useState(readDock);
  const [mounted, setMounted] = useState(dock.mode !== "closed"); // keeps the chat once started
  const [prefill, setPrefill] = useState({ text: "", n: 0 });
  const params = Object.assign({}, ...useMatches().map((m) => m.params)) as Record<
    string,
    string | undefined
  >;
  const projectId = params.projectId;
  const page = pageContext(params);
  const shown = wide && dock.mode !== "closed";

  const setMode = (mode: Dock["mode"]) => {
    if (mode !== "closed") setMounted(true);
    if (mode === "open") announcePanel("assistant");
    setDock((d) => ({ ...d, mode }));
  };
  useEffect(() => {
    try {
      localStorage.setItem(DOCK_KEY, JSON.stringify(dock));
    } catch {
      // storage is blocked: the choice lasts until the page reloads
    }
  }, [dock]);
  // the page makes room: AppShell pads itself by this
  useEffect(() => {
    if (!shown) return;
    document.documentElement.style.setProperty(
      "--assistant-w",
      `${dock.mode === "strip" ? STRIP_W : dock.width}px`,
    );
    return () => {
      document.documentElement.style.removeProperty("--assistant-w");
    };
  }, [shown, dock]);

  useEffect(() => {
    const onOther = (e: Event) => {
      if ((e as CustomEvent<PanelName>).detail !== "google") return;
      setDock((d) => ({ ...d, mode: "closed" }));
      setOpen(false);
    };
    window.addEventListener(PANEL_OPENED, onOther);
    return () => window.removeEventListener(PANEL_OPENED, onOther);
  }, []);

  const toggle = () =>
    wide
      ? setMode(dock.mode === "open" ? "closed" : "open")
      : (announcePanel("assistant"), setOpen(!open));
  const toggleRef = useRef(toggle);
  useEffect(() => {
    toggleRef.current = toggle;
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === ".") {
        e.preventDefault();
        toggleRef.current();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => {
    const onPrefill = (e: Event) => {
      setPrefill((p) => ({ text: (e as CustomEvent<string>).detail, n: p.n + 1 }));
      if (wide) setMode("open");
      else setOpen(true);
    };
    window.addEventListener(ASSISTANT_PREFILL, onPrefill);
    return () => window.removeEventListener(ASSISTANT_PREFILL, onPrefill);
  }, [wide]);

  const button = (
    <Button
      variant="secondary"
      size="sm"
      aria-label="Assistant"
      title={`Assistant (${MOD_KEY} .)`}
      aria-expanded={wide ? dock.mode === "open" : undefined}
      onClick={wide ? toggle : undefined}
    >
      <Sparkles aria-hidden />
      <span className="hidden sm:inline">Assistant</span>
    </Button>
  );

  if (wide)
    return (
      <>
        {button}
        {mounted && (
          <aside
            aria-label="Assistant"
            style={{ width: dock.mode === "strip" ? STRIP_W : dock.width }}
            className={`fixed inset-y-0 right-0 z-30 border-l bg-background print:hidden ${
              dock.mode === "strip" ? "flex-col items-center bg-muted" : ""
            } ${dock.mode === "closed" ? "hidden" : "flex"}`}
          >
            {dock.mode === "strip" && (
              <Button
                variant="ghost"
                size="icon"
                className="mx-auto mt-3"
                aria-label="Open the assistant"
                title={`Open the assistant (${MOD_KEY} .)`}
                onClick={() => setMode("open")}
              >
                <PanelRightOpen aria-hidden />
              </Button>
            )}
            {dock.mode === "strip" && (
              <span
                aria-hidden
                className="mt-3 text-xs font-medium text-muted-foreground [writing-mode:vertical-rl]"
              >
                Assistant
              </span>
            )}
            <div
              className={
                dock.mode === "open" ? "flex min-h-0 min-w-0 flex-1 flex-col gap-3 p-4" : "hidden"
              }
            >
              <AssistantPanel
                key={labId}
                labId={labId}
                projectId={projectId}
                page={page}
                prefill={prefill}
                docked
                onClose={() => setMode("closed")}
                onCollapse={() => setMode("strip")}
              />
            </div>
            {dock.mode === "open" && (
              <DockHandle
                label="Resize the assistant"
                width={dock.width}
                min={MIN_W}
                max={MAX_W}
                onWidth={(w) => setDock((d) => ({ ...d, width: clampWidth(w) }))}
              />
            )}
          </aside>
        )}
      </>
    );

  return (
    <Sheet
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setPrefill({ text: "", n: prefill.n });
      }}
    >
      <SheetTrigger asChild>{button}</SheetTrigger>
      <SheetContent className="max-w-xl gap-3 p-4" aria-describedby={undefined}>
        <AssistantPanel
          key={`${labId}:${projectId ?? ""}`}
          labId={labId}
          projectId={projectId}
          page={page}
          initialText={prefill.text}
          onClose={() => setOpen(false)}
        />
      </SheetContent>
    </Sheet>
  );
}
