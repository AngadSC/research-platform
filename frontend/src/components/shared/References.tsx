import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Reference } from "@/lib/api-types";
import { doiHref, MAX_REFERENCES, moveRow, urlHref, type RefErrors } from "@/lib/references";

const ext = { target: "_blank", rel: "noopener noreferrer" } as const;
const link = "text-primary hover:underline";

/** Read-only list. Links only for http(s) URLs and well-formed DOIs. */
export function ReferenceList({ items }: { items: Reference[] }) {
  if (items.length === 0) return <>None</>;
  return (
    <ul className="grid gap-1">
      {items.map((x, i) => {
        const url = x.url ? urlHref(x.url) : null;
        const doi = x.doi ? doiHref(x.doi) : null;
        return (
          <li key={i}>
            {url ? (
              <a className={link} href={url} {...ext}>
                {x.title}
              </a>
            ) : (
              x.title
            )}
            {x.doi && (
              <>
                {" "}
                {doi ? (
                  <a className={link} href={doi} {...ext}>
                    DOI {x.doi}
                  </a>
                ) : (
                  <span>DOI {x.doi}</span>
                )}
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}

interface EditorProps {
  rows: Reference[];
  errors: RefErrors[];
  onChange: (rows: Reference[]) => void;
}

/** Add, remove and reorder rows (up and down buttons, so it works without dragging). */
export function ReferencesEditor({ rows, errors, onChange }: EditorProps) {
  const set = (i: number, patch: Partial<Reference>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <fieldset className="grid gap-3">
      <legend className="text-sm font-medium">References</legend>
      {rows.length === 0 && <p className="text-xs text-muted-foreground">No references yet.</p>}
      {rows.map((r, i) => (
        <div
          key={i}
          role="group"
          aria-label={`Reference ${i + 1}`}
          className="grid gap-2 rounded-md border p-2"
        >
          <div className="grid gap-2 sm:grid-cols-3">
            <Cell label="Title" error={errors[i]?.title}>
              {(p) => (
                <Input
                  maxLength={300}
                  {...p}
                  value={r.title}
                  onChange={(e) => set(i, { title: e.target.value })}
                />
              )}
            </Cell>
            <Cell label="Link" error={errors[i]?.url}>
              {(p) => (
                <Input
                  maxLength={500}
                  {...p}
                  type="url"
                  value={r.url ?? ""}
                  onChange={(e) => set(i, { url: e.target.value })}
                />
              )}
            </Cell>
            <Cell label="DOI" error={errors[i]?.doi}>
              {(p) => (
                <Input
                  maxLength={200}
                  {...p}
                  placeholder="10.1234/abcd"
                  value={r.doi ?? ""}
                  onChange={(e) => set(i, { doi: e.target.value })}
                />
              )}
            </Cell>
          </div>
          <div className="flex justify-end gap-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={i === 0}
              aria-label={`Move reference ${i + 1} up`}
              onClick={() => onChange(moveRow(rows, i, i - 1))}
            >
              <ArrowUp aria-hidden />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={i === rows.length - 1}
              aria-label={`Move reference ${i + 1} down`}
              onClick={() => onChange(moveRow(rows, i, i + 1))}
            >
              <ArrowDown aria-hidden />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label={`Remove reference ${i + 1}`}
              onClick={() => onChange(rows.filter((_, j) => j !== i))}
            >
              <Trash2 aria-hidden />
            </Button>
          </div>
        </div>
      ))}
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={rows.length >= MAX_REFERENCES}
          onClick={() => onChange([...rows, { title: "", url: "", doi: "" }])}
        >
          <Plus aria-hidden /> Add a reference
        </Button>
      </div>
    </fieldset>
  );
}

function Cell({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: (p: { id?: string; "aria-label": string; "aria-invalid"?: boolean }) => React.ReactNode;
}) {
  return (
    <div className="grid content-start gap-1">
      <Label className="text-xs">{label}</Label>
      {children({ "aria-label": label, "aria-invalid": error ? true : undefined })}
      {error && (
        <p role="alert" className="text-xs font-medium text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
