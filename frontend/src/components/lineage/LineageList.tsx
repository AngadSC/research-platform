import { KIND_STYLE } from "@/components/lineage/kinds";
import type { Lineage, LineageNode } from "@/lib/api-types";
import {
  COLUMN_KINDS,
  COLUMN_TITLES,
  indexLineage,
  KIND_LABEL,
  layoutLineage,
  metaStr,
  upstreamChain,
  type ChainNode,
} from "@/lib/lineage";

/** One plain-text line of key facts, so screen readers get the same chain the panel shows. */
function plain(n: LineageNode): string {
  const m = (k: string) => metaStr(n, k);
  switch (n.kind) {
    case "dataset":
      return [m("version_label"), m("checksum") && `checksum ${m("checksum")}`]
        .filter(Boolean)
        .join(", ");
    case "analysis":
      return [m("code_repo_url"), m("code_commit") && `commit ${m("code_commit")}`]
        .filter(Boolean)
        .join(", ");
    case "manuscript":
      return m("status").replace(/_/g, " ");
    default:
      return n.subtitle;
  }
}

function Nested({ label, items }: { label: string; items: ChainNode[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-1 ml-4 border-l pl-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <ul className="grid gap-1">
        {items.map(({ node, children }) => (
          <li key={node.id} className="text-sm">
            <span className="font-medium">{node.label}</span>{" "}
            <span className="text-xs text-muted-foreground">
              {KIND_LABEL[node.kind]}
              {plain(node) && ` · ${plain(node)}`}
            </span>
            <Nested label="Built from" items={children} />
          </li>
        ))}
      </ul>
    </div>
  );
}

interface Props {
  data: Lineage;
  onSelect: (id: string) => void;
}

/** The whole lineage as nested lists: the accessible twin of the canvas. */
export function LineageList({ data, onSelect }: Props) {
  const ix = indexLineage(data);
  const order = layoutLineage(data).nodes.map((p) => p.id);
  const kinds = [...COLUMN_KINDS, "decision"] as const;
  return (
    <div className="grid gap-8" data-testid="lineage-list">
      {kinds.map((kind) => {
        const nodes = order.flatMap((id) =>
          ix.byId.get(id)?.kind === kind ? [ix.byId.get(id)!] : [],
        );
        if (!nodes.length) return null;
        const { icon: Icon } = KIND_STYLE[kind];
        return (
          <section key={kind} aria-labelledby={`lineage-list-${kind}`} className="grid gap-3">
            <h3
              id={`lineage-list-${kind}`}
              className="flex items-center gap-2 text-base font-semibold"
            >
              <Icon className="size-4 text-muted-foreground" aria-hidden />
              {COLUMN_TITLES[kind]}
            </h3>
            <ul className="grid gap-3">
              {nodes.map((n) => {
                const children = upstreamChain(ix, n.id)?.children ?? [];
                const applies = (ix.applies.get(n.id) ?? []).flatMap((id) => {
                  const t = ix.byId.get(id);
                  return t ? [{ node: t, children: [] }] : [];
                });
                return (
                  <li key={n.id} className="rounded-lg border p-3">
                    <button
                      type="button"
                      onClick={() => onSelect(n.id)}
                      className="rounded-sm text-left text-sm font-medium hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                    >
                      {n.label}
                    </button>{" "}
                    <span className="text-xs text-muted-foreground">{plain(n)}</span>
                    <Nested label="Built from" items={children} />
                    <Nested label="Applies to" items={applies} />
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
