import {
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import {
  AtSign,
  Bold,
  Code,
  Italic,
  Link as LinkIcon,
  List,
  ListOrdered,
  Quote,
  Send,
  Smile,
  SquareCode,
  Strikethrough,
} from "lucide-react";
import { EmojiPicker } from "@/components/composer/EmojiPicker";
import { Button } from "@/components/ui/button";
import {
  applyMention,
  cleanUrl,
  codeBlock,
  insertLink,
  insertText,
  mentionAt,
  prefixLines,
  wrap,
  type Edit,
} from "@/lib/composerFormat";
import { cn } from "@/lib/utils";

export interface Person {
  id: string;
  name: string;
}

type Actions = Record<
  "bold" | "italic" | "strike" | "code" | "codeBlock" | "numbered" | "bullets" | "quote" | "link",
  () => void
>;

const TOOLBAR_KEY = "composer-toolbar";
const MAX_SUGGESTIONS = 6;

function readToolbarPref() {
  try {
    return localStorage.getItem(TOOLBAR_KEY) !== "0";
  } catch {
    return true;
  }
}

const TOOLS: ([string, string, typeof Bold, keyof Actions] | "|")[] = [
  ["Bold", "Ctrl+B", Bold, "bold"],
  ["Italic", "Ctrl+I", Italic, "italic"],
  ["Strikethrough", "Ctrl+Shift+X", Strikethrough, "strike"],
  "|",
  ["Link", "Ctrl+K", LinkIcon, "link"],
  "|",
  ["Numbered list", "", ListOrdered, "numbered"],
  ["Bulleted list", "", List, "bullets"],
  "|",
  ["Quote", "", Quote, "quote"],
  "|",
  ["Inline code", "Ctrl+E", Code, "code"],
  ["Code block", "", SquareCode, "codeBlock"],
];

const mod = (e: KeyboardEvent) => (e.ctrlKey || e.metaKey) && !e.altKey;

/** A message box with a formatting toolbar, emoji, @mentions and send on Enter (D260). It is a
 * plain textarea holding simple markdown, so what is stored is what `MessageText` renders. Put it
 * inside a `<form>`: Enter, and the Send button, submit that form. */
export function RichComposer({
  value,
  onChange,
  ariaLabel,
  placeholder,
  maxLength,
  rows = 2,
  people,
  enterToSend = false,
  submitLabel,
  submitting = false,
  className,
  footer,
}: {
  value: string;
  onChange: (value: string) => void;
  ariaLabel: string;
  placeholder?: string;
  maxLength?: number;
  rows?: number;
  /** Who can be @mentioned here. Leave out to switch mentions off. */
  people?: Person[];
  /** Enter sends and Shift+Enter adds a line; otherwise Ctrl/Cmd+Enter sends. */
  enterToSend?: boolean;
  /** Shows a Send button with this label. */
  submitLabel?: string;
  submitting?: boolean;
  className?: string;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const pending = useRef<Edit>(undefined);
  const uid = useId();
  const [showToolbar, setShowToolbar] = useState(readToolbarPref);
  const [caret, setCaret] = useState(0);
  const [active, setActive] = useState(0);
  const [dismissed, setDismissed] = useState<number>();
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [link, setLink] = useState<{ start: number; end: number }>();
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState("");

  // Put the caret where an edit says, once React has the new text in the box.
  useLayoutEffect(() => {
    const p = pending.current;
    const el = ref.current;
    if (!p || !el) return;
    pending.current = undefined;
    el.focus();
    el.setSelectionRange(p.start, p.end);
    setCaret(p.end);
  }, [value]);

  const at = people ? mentionAt(value, caret) : null;
  const q = at?.query.toLowerCase() ?? "";
  const matches =
    at && at.start !== dismissed
      ? (people ?? []).filter((p) => p.name.toLowerCase().includes(q)).slice(0, MAX_SUGGESTIONS)
      : [];
  const listOpen = matches.length > 0;
  const current = Math.min(active, matches.length - 1);
  const optionId = (i: number) => `${uid}-person-${i}`;

  function apply(edit: Edit) {
    pending.current = edit;
    onChange(edit.value);
  }
  const sel = () =>
    [
      ref.current?.selectionStart ?? value.length,
      ref.current?.selectionEnd ?? value.length,
    ] as const;
  const format = (fn: (s: number, e: number) => Edit) => {
    const [s, e] = sel();
    apply(fn(s, e));
  };
  const actions: Actions = {
    bold: () => format((s, e) => wrap(value, s, e, "**", "**", "bold")),
    italic: () => format((s, e) => wrap(value, s, e, "_", "_", "italic")),
    strike: () => format((s, e) => wrap(value, s, e, "~~", "~~", "strike")),
    code: () => format((s, e) => wrap(value, s, e, "`", "`", "code")),
    codeBlock: () => format((s, e) => codeBlock(value, s, e)),
    numbered: () => format((s, e) => prefixLines(value, s, e, "number")),
    bullets: () => format((s, e) => prefixLines(value, s, e, "bullet")),
    quote: () => format((s, e) => prefixLines(value, s, e, "quote")),
    link: () => {
      const [start, end] = sel();
      setLink({ start, end });
      setUrl("");
      setUrlError("");
      setEmojiOpen(false);
    },
  };

  function addLink() {
    const clean = cleanUrl(url);
    if (!clean || !link) {
      setUrlError("Enter a web address (https://...) or an email address.");
      return;
    }
    const { start, end } = link;
    setLink(undefined);
    apply(insertLink(value, start, end, clean));
  }

  function insertAtCaret(text: string) {
    const [s, e] = sel();
    apply(insertText(value, s, e, text));
  }

  function pick(person: Person) {
    if (at) apply(applyMention(value, at, person.name, person.id));
  }

  function startMention() {
    const [s, e] = sel();
    const before = value.slice(0, s);
    apply(insertText(value, s, e, before && !/\s$/.test(before) ? " @" : "@"));
  }

  function toggleToolbar() {
    const next = !showToolbar;
    setShowToolbar(next);
    try {
      localStorage.setItem(TOOLBAR_KEY, next ? "1" : "0");
    } catch {
      /* the choice just isn't remembered */
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (listOpen) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const step = e.key === "ArrowDown" ? 1 : -1;
        setActive((current + step + matches.length) % matches.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        pick(matches[current]!);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setDismissed(at?.start);
        return;
      }
    }
    if (mod(e)) {
      const key = e.key.toLowerCase();
      const run = (fn: () => void) => {
        e.preventDefault();
        fn();
      };
      if (key === "b" && !e.shiftKey) return run(actions.bold);
      if (key === "i" && !e.shiftKey) return run(actions.italic);
      if (key === "k" && !e.shiftKey) return run(actions.link);
      if (key === "e" && !e.shiftKey) return run(actions.code);
      if (key === "x" && e.shiftKey) return run(actions.strike);
    }
    if (e.key === "Enter" && !e.nativeEvent.isComposing) {
      const send = enterToSend ? !e.shiftKey && !mod(e) : mod(e);
      if (send) {
        e.preventDefault();
        if (value.trim()) e.currentTarget.form?.requestSubmit();
      } else if (enterToSend && mod(e)) {
        e.preventDefault(); // Ctrl+Enter is a line break too, as in most chats
        insertAtCaret("\n");
      }
    }
  }

  function onToolbarKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
    if (!keys.includes(e.key)) return;
    const buttons = Array.from(toolbarRef.current?.querySelectorAll("button") ?? []);
    const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
    if (i < 0) return;
    e.preventDefault();
    const to =
      e.key === "Home"
        ? 0
        : e.key === "End"
          ? buttons.length - 1
          : i + (e.key === "ArrowRight" ? 1 : -1);
    buttons[(to + buttons.length) % buttons.length]?.focus();
  }

  return (
    <div className={cn("grid gap-1", className)}>
      <div className="relative rounded-md border border-input bg-card focus-within:ring-2 focus-within:ring-ring">
        {showToolbar && (
          <div
            ref={toolbarRef}
            id={`${uid}-toolbar`}
            role="toolbar"
            aria-label="Formatting"
            onKeyDown={onToolbarKeyDown}
            className="flex flex-wrap items-center gap-0.5 border-b px-1.5 py-1"
          >
            {TOOLS.map((t, i) =>
              t === "|" ? (
                <span key={i} aria-hidden className="mx-1 h-4 w-px bg-border" />
              ) : (
                <ToolButton
                  key={t[0]}
                  label={t[0]}
                  shortcut={t[1]}
                  icon={t[2]}
                  onClick={() => actions[t[3]]()}
                />
              ),
            )}
          </div>
        )}

        {link && (
          <div className="flex flex-wrap items-center gap-2 border-b bg-muted/50 px-2 py-1.5">
            <label htmlFor={`${uid}-url`} className="sr-only">
              Link address
            </label>
            <input
              id={`${uid}-url`}
              autoFocus
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setUrlError("");
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addLink();
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  setLink(undefined);
                  ref.current?.focus();
                }
              }}
              placeholder="https://example.org"
              aria-invalid={!!urlError}
              aria-describedby={urlError ? `${uid}-url-error` : undefined}
              className="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            />
            <Button type="button" size="sm" onClick={addLink}>
              Add link
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                setLink(undefined);
                ref.current?.focus();
              }}
            >
              Cancel
            </Button>
            {urlError && (
              <p id={`${uid}-url-error`} role="alert" className="w-full text-xs text-destructive">
                {urlError}
              </p>
            )}
          </div>
        )}

        <textarea
          ref={ref}
          aria-label={ariaLabel}
          aria-autocomplete={people ? "list" : undefined}
          aria-controls={listOpen ? `${uid}-people` : undefined}
          aria-activedescendant={listOpen ? optionId(current) : undefined}
          value={value}
          maxLength={maxLength}
          rows={rows}
          placeholder={placeholder}
          onChange={(e) => {
            onChange(e.target.value);
            setCaret(e.target.selectionStart);
            setActive(0);
            if (people && !mentionAt(e.target.value, e.target.selectionStart))
              setDismissed(undefined);
          }}
          onSelect={(e) => setCaret(e.currentTarget.selectionStart)}
          onKeyDown={onKeyDown}
          className="block max-h-40 min-h-11 w-full resize-none bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none disabled:opacity-50"
        />

        {listOpen && (
          <ul
            id={`${uid}-people`}
            role="listbox"
            aria-label="People you can mention"
            className="absolute right-2 bottom-full left-2 z-20 mb-1 max-h-48 overflow-y-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
          >
            {matches.map((p, i) => (
              <li
                key={p.id}
                id={optionId(i)}
                role="option"
                aria-selected={i === current}
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(p);
                }}
                onMouseEnter={() => setActive(i)}
                className={cn(
                  "cursor-pointer truncate rounded px-2 py-1.5 text-sm",
                  i === current && "bg-accent text-accent-foreground",
                )}
              >
                {p.name}
              </li>
            ))}
          </ul>
        )}

        <div className="flex items-center gap-1 px-1.5 pb-1.5">
          <div className="relative">
            <ToolButton
              label="Emoji"
              icon={Smile}
              pressed={emojiOpen}
              onClick={() => {
                setEmojiOpen((o) => !o);
                setLink(undefined);
              }}
            />
            {emojiOpen && (
              <EmojiPicker
                onClose={() => setEmojiOpen(false)}
                onPick={(emoji) => {
                  setEmojiOpen(false);
                  insertAtCaret(emoji);
                }}
              />
            )}
          </div>
          {people && <ToolButton label="Mention someone" icon={AtSign} onClick={startMention} />}
          <button
            type="button"
            aria-label="Formatting"
            aria-pressed={showToolbar}
            aria-controls={`${uid}-toolbar`}
            title="Show or hide formatting"
            onMouseDown={(e) => e.preventDefault()}
            onClick={toggleToolbar}
            className={cn(
              "inline-flex h-8 min-w-8 items-center justify-center rounded-md px-1.5 text-sm font-semibold text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              showToolbar && "bg-accent text-accent-foreground",
            )}
          >
            Aa
          </button>
          {submitLabel && (
            <Button
              type="submit"
              size="sm"
              className="ml-auto"
              disabled={!value.trim() || submitting}
            >
              <Send aria-hidden /> {submitLabel}
            </Button>
          )}
        </div>
      </div>
      {footer}
    </div>
  );
}

function ToolButton({
  label,
  shortcut,
  icon: Icon,
  onClick,
  pressed,
}: {
  label: string;
  shortcut?: string;
  icon: typeof Bold;
  onClick: () => void;
  pressed?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={pressed}
      title={shortcut ? `${label} (${shortcut})` : label}
      // Keep the caret and selection in the text box while a button is used.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none aria-pressed:bg-accent aria-pressed:text-accent-foreground [&_svg]:size-4"
    >
      <Icon aria-hidden />
    </button>
  );
}
