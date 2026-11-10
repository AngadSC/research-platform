import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { FieldControlProps } from "@/components/shared/FormField";
import { Input } from "@/components/ui/input";
import { useDebounced } from "@/hooks/useDebounced";
import { api } from "@/lib/api";
import type { InstitutionHit } from "@/lib/api-types";

const webSearch = (text: string) => `https://www.google.com/search?q=${encodeURIComponent(text)}`;

/** A free-text institution field with suggestions from the ROR registry (D237). Anything can
 * still be typed, so it works the same when the registry has no match or cannot be reached. */
export function InstitutionInput({
  name,
  defaultValue = "",
  onPick,
  ...field
}: FieldControlProps & {
  name: string;
  defaultValue?: string;
  onPick?: (hit: InstitutionHit) => void;
}) {
  const [text, setText] = useState(defaultValue);
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<InstitutionHit>();
  const q = useDebounced(text.trim());
  const search = useQuery({
    queryKey: ["institution-search", q],
    queryFn: () =>
      api<{ results: InstitutionHit[] }>(`/api/institutions/search/?q=${encodeURIComponent(q)}`),
    enabled: open && q.length >= 2,
    staleTime: 60 * 60 * 1000,
  });
  const hits = open ? (search.data?.results ?? []) : [];

  function pick(hit: InstitutionHit) {
    setText(hit.name);
    setPicked(hit);
    setOpen(false);
    onPick?.(hit);
  }

  return (
    <div
      className="grid gap-1.5"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
      }}
    >
      <Input
        {...field}
        name={name}
        value={text}
        autoComplete="off"
        onChange={(e) => {
          setText(e.target.value);
          setPicked(undefined);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
      />
      {hits.length > 0 && (
        <ul
          aria-label="Suggested institutions"
          className="grid max-h-60 divide-y overflow-y-auto rounded-lg border bg-background"
        >
          {hits.map((h) => (
            <li key={h.id}>
              <button
                type="button"
                className="grid w-full px-3 py-2 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
                onClick={() => pick(h)}
              >
                <span className="font-medium">{h.name}</span>
                {h.address && <span className="text-xs text-muted-foreground">{h.address}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {picked && (
        <p className="text-xs text-muted-foreground">
          Filled in from the Research Organization Registry. Check it and add what is missing, such
          as the postal code. To find this institution's own pages, try a{" "}
          <a
            className="underline underline-offset-4"
            href={webSearch(`${picked.name} research ethics board`)}
            target="_blank"
            rel="noreferrer noopener"
          >
            web search for its ethics pages
          </a>{" "}
          or a{" "}
          <a
            className="underline underline-offset-4"
            href={webSearch(`${picked.name} research funding office`)}
            target="_blank"
            rel="noreferrer noopener"
          >
            web search for its funding pages
          </a>
          . These are plain web searches, so check that what you find is really theirs.
        </p>
      )}
    </div>
  );
}
