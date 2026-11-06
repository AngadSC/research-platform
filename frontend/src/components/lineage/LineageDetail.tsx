import { Copy, ExternalLink, HardDrive } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { KIND_STYLE } from "@/components/lineage/kinds";
import { DetailPanel } from "@/components/shared/DetailPanel";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import type { LineageNode } from "@/lib/api-types";
import { when } from "@/lib/format";
import {
  decisionsFor,
  KIND_LABEL,
  metaStr,
  recordPath,
  safeHttpUrl,
  upstreamChain,
  usedBy,
  type ChainNode,
  type Index,
} from "@/lib/lineage";
import { cn } from "@/lib/utils";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm">{children}</dd>
    </div>
  );
}

function CopyField({ label, value }: { label: string; value: string }) {
  if (!value) return <span className="text-muted-foreground">Not recorded</span>;
  return (
    <span className="flex items-start gap-1 rounded-md border bg-muted px-2 py-1">
      <code className="min-w-0 flex-1 font-mono text-xs break-all">{value}</code>
      <button
        type="button"
        aria-label={`Copy ${label.toLowerCase()}`}
        className="shrink-0 rounded-sm p-0.5 text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        onClick={() =>
          navigator.clipboard
            ?.writeText(value)
            .then(() => toast.success("Copied"))
            .catch(() => toast.error("Could not copy. Select the text and copy it instead."))
        }
      >
        <Copy className="size-3.5" />
      </button>
    </span>
  );
}

function ExtLink({ url, label }: { url: string; label?: string }) {
  const href = safeHttpUrl(url);
  if (!url) return <span className="text-muted-foreground">Not recorded</span>;
  if (!href) return <span className="break-all">{url}</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 break-all text-primary underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      {label ?? url}
      <ExternalLink className="size-3 shrink-0" aria-hidden />
    </a>
  );
}

const LINK_STATUS: Record<string, string> = {
  ok: "Up to date",
  changed: "Changed since linked",
  unavailable: "No longer available",
};
interface OutsideLink {
  id: string;
  provider: string;
  title: string;
  url: string;
  status: string;
}

/** Outside files (for example Google Drive) linked to this node, with their status. */
function OutsideLinks({ node }: { node: LineageNode }) {
  const links = (node.meta.external_links ?? []) as OutsideLink[];
  if (!links.length) return null;
  return (
    <dl className="grid gap-2">
      <Field label="Linked files">
        <ul className="grid gap-1">
          {links.map((l) => (
            <li key={l.id} className="flex flex-wrap items-center gap-x-2">
              <HardDrive className="size-3.5 text-muted-foreground" aria-hidden />
              <ExtLink url={l.url} label={l.title} />
              <span className="text-xs text-muted-foreground">
                {LINK_STATUS[l.status] ?? l.status}
              </span>
            </li>
          ))}
        </ul>
      </Field>
    </dl>
  );
}

/** Key facts for one node, by kind. */
function Facts({ node }: { node: LineageNode }) {
  return (
    <>
      <KindFacts node={node} />
      <OutsideLinks node={node} />
    </>
  );
}

function KindFacts({ node }: { node: LineageNode }) {
  const m = (k: string) => metaStr(node, k);
  switch (node.kind) {
    case "dataset":
      return (
        <dl className="grid gap-2">
          <Field label="Version">{m("version_label") || "Not recorded"}</Field>
          <Field label="Checksum">
            <CopyField label="Checksum" value={m("checksum")} />
          </Field>
          {m("location_url") ? (
            <Field label="Where it lives">
              <ExtLink url={m("location_url")} />
            </Field>
          ) : (
            m("location_text") && <Field label="Where it lives">{m("location_text")}</Field>
          )}
        </dl>
      );
    case "analysis":
      return (
        <dl className="grid gap-2">
          <Field label="Code repository">
            <ExtLink url={m("code_repo_url")} />
          </Field>
          <Field label="Commit">
            {m("code_commit") || !node.meta.code_attachment_id ? (
              <CopyField label="Commit" value={m("code_commit")} />
            ) : (
              "Code attached as a file"
            )}
          </Field>
          {m("ran_by") && (
            <Field label="Run by">
              {m("ran_by")}
              {m("ran_at") && <span className="text-muted-foreground"> · {when(m("ran_at"))}</span>}
            </Field>
          )}
        </dl>
      );
    case "result":
      return m("summary") ? (
        <p className="text-sm whitespace-pre-line text-muted-foreground">{m("summary")}</p>
      ) : null;
    case "manuscript":
      return (
        <dl className="grid gap-2">
          <Field label="Status">
            <StatusBadge status={m("status")} />
          </Field>
          <Field label="Link">
            <ExtLink url={m("url")} />
          </Field>
        </dl>
      );
    case "decision":
      return (
        <dl className="grid gap-2">
          <Field label="Decided on">{m("decided_on")}</Field>
          {m("rationale") && <Field label="Why">{m("rationale")}</Field>}
        </dl>
      );
  }
}

function Title({ node }: { node: LineageNode }) {
  const { icon: Icon, chip } = KIND_STYLE[node.kind];
  return (
    <div className="flex items-center gap-2">
      <span className={cn("flex size-6 shrink-0 items-center justify-center rounded-md", chip)}>
        <Icon className="size-3.5" />
      </span>
      <span className="min-w-0 text-sm font-medium">{node.label}</span>
      <span className="text-xs text-muted-foreground">{KIND_LABEL[node.kind]}</span>
    </div>
  );
}

function Chain({ items }: { items: ChainNode[] }) {
  return (
    <ul className="grid gap-3">
      {items.map(({ node, children }) => (
        <li key={node.id} className="grid gap-2">
          <div className="grid gap-2 rounded-lg border p-3">
            <Title node={node} />
            <Facts node={node} />
          </div>
          {children.length > 0 && (
            <div className="ml-3 grid gap-2 border-l pl-3">
              <p className="text-xs text-muted-foreground">Built from</p>
              <Chain items={children} />
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-3">
      <h3 className="text-base font-semibold">{title}</h3>
      {children}
    </section>
  );
}

const Empty = ({ children }: { children: ReactNode }) => (
  <p className="text-sm text-muted-foreground">{children}</p>
);

interface Props {
  ix: Index;
  node: LineageNode | null;
  labId: string;
  projectId: string;
  onSelect: (id: string) => void;
  onClose: () => void;
}

export function LineageDetail({ ix, node, labId, projectId, onSelect, onClose }: Props) {
  const upstream = node ? (upstreamChain(ix, node.id)?.children ?? []) : [];
  const downstream = node ? usedBy(ix, node.id) : [];
  const decisions = node ? decisionsFor(ix, node.id) : [];
  const applies = node && node.kind === "decision" ? (ix.applies.get(node.id) ?? []) : [];

  const pick = (n: LineageNode, extra?: ReactNode) => (
    <li key={n.id}>
      <button
        type="button"
        onClick={() => onSelect(n.id)}
        className="flex w-full flex-col rounded-md border px-3 py-2 text-left text-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <span className="font-medium">{n.label}</span>
        <span className="text-xs text-muted-foreground">
          {KIND_LABEL[n.kind]}
          {extra}
        </span>
      </button>
    </li>
  );

  return (
    <DetailPanel
      open={!!node}
      onOpenChange={(o) => !o && onClose()}
      title={node?.label ?? ""}
      description={node ? KIND_LABEL[node.kind] : undefined}
    >
      {node && (
        <div className="flex flex-col gap-8 pb-6">
          <Facts node={node} />
          {node.kind === "decision" ? (
            <Section title="Applies to">
              {applies.length ? (
                <ul className="grid gap-2">
                  {applies.flatMap((id) => ix.byId.get(id) ?? []).map((n) => pick(n))}
                </ul>
              ) : (
                <Empty>This decision is not attached to anything yet.</Empty>
              )}
            </Section>
          ) : (
            <>
              <Section title="Upstream">
                {upstream.length ? (
                  <Chain items={upstream} />
                ) : (
                  <Empty>
                    {node.kind === "dataset"
                      ? "No earlier versions. This is the source."
                      : "Nothing is connected upstream yet."}
                  </Empty>
                )}
              </Section>
              <Section title="Used by">
                {downstream.length ? (
                  <ul className="grid gap-2">{downstream.map((n) => pick(n))}</ul>
                ) : (
                  <Empty>Nothing builds on this yet.</Empty>
                )}
              </Section>
              <Section title="Decisions">
                {decisions.length ? (
                  <ul className="grid gap-2">
                    {decisions.map(({ decision, appliesTo }) =>
                      pick(decision, <> · applies to {appliesTo.map((a) => a.label).join(", ")}</>),
                    )}
                  </ul>
                ) : (
                  <Empty>No decisions are attached here.</Empty>
                )}
              </Section>
            </>
          )}
          <Button asChild variant="outline" className="self-start">
            <Link to={`/labs/${labId}/projects/${projectId}/${recordPath(node)}`}>
              Open full record
            </Link>
          </Button>
        </div>
      )}
    </DetailPanel>
  );
}
