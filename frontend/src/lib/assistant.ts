import { ApiError, getCookie, SESSION_URL, toApiError } from "@/lib/api";

export const ASSISTANT_PREFILL = "assistant:prefill";

/** Opens the assistant drawer with `prompt` in the message box, not sent. */
export const openAssistant = (prompt: string) =>
  window.dispatchEvent(new CustomEvent(ASSISTANT_PREFILL, { detail: prompt }));

/** One server-sent event from the assistant (D190). `type` is the SSE event name. */
export interface ChatEvent {
  type: string;
  [key: string]: unknown;
}

/** Splits a text/event-stream body into events. Comment lines (": keepalive") are ignored. */
export function parseSse(buffer: string): { events: ChatEvent[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: ChatEvent[] = [];
  for (const part of parts) {
    const data = part
      .split("\n")
      .filter((l) => l.startsWith("data: "))
      .map((l) => l.slice(6))
      .join("\n");
    if (!data) continue;
    try {
      events.push(JSON.parse(data) as ChatEvent);
    } catch {
      /* a damaged chunk is skipped, never fatal */
    }
  }
  return { events, rest };
}

/**
 * POSTs JSON and reads the answer as it arrives (fetch, not EventSource: EventSource cannot POST
 * or send the CSRF header). Rejects with ApiError for any non-2xx answer before the stream starts
 * (policy, no key, busy). Resolves when the stream ends or is aborted.
 */
export async function streamPost(
  path: string,
  body: unknown,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (!getCookie("csrftoken")) {
    await fetch(SESSION_URL, { headers: { Accept: "application/json" } });
  }
  let res: Response;
  try {
    res = await fetch(path, {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken") ?? "",
      },
      credentials: "same-origin",
      signal,
      body: JSON.stringify(body),
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") return;
    throw new ApiError(0, "We couldn't reach the server. Check your connection and try again.");
  }
  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      /* not JSON */
    }
    throw toApiError(res.status, parsed);
  }
  const decoder = new TextDecoder();
  let buffer = "";
  const feed = (chunk: string) => {
    buffer += chunk;
    const { events, rest } = parseSse(buffer);
    buffer = rest;
    events.forEach(onEvent);
  };
  try {
    if (res.body) {
      const reader = res.body.getReader();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        feed(decoder.decode(value, { stream: true }));
      }
    } else {
      feed(await res.text());
    }
    feed("\n\n");
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") return;
    throw new ApiError(0, "The connection dropped while the assistant was answering.");
  }
}

export interface Usage {
  input_tokens?: number;
  output_tokens?: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
}

export interface Price {
  input: number;
  output: number;
}

/** Tokens the model read, counting cached ones. */
export const tokensIn = (u: Usage) =>
  (u.input_tokens ?? 0) + (u.cache_read_tokens ?? 0) + (u.cache_write_tokens ?? 0);

/**
 * A rough dollar figure from list prices (USD per million tokens). Cached reads are priced at a
 * tenth and Anthropic cache writes at 1.25 times; it is an estimate, not a bill.
 */
export function estimateCost(u: Usage, p: Price | undefined): number | null {
  if (!p) return null;
  const inCost =
    (u.input_tokens ?? 0) * p.input +
    (u.cache_read_tokens ?? 0) * p.input * 0.1 +
    (u.cache_write_tokens ?? 0) * p.input * 1.25;
  return (inCost + (u.output_tokens ?? 0) * p.output) / 1_000_000;
}

export const formatCost = (c: number) => (c < 0.01 ? "under $0.01" : `about $${c.toFixed(2)}`);
