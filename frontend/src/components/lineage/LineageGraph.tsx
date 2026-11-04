import {
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { KIND_STYLE } from "@/components/lineage/kinds";
import type { Lineage, LineageNode } from "@/lib/api-types";
import {
  highlightSet,
  indexLineage,
  KIND_LABEL,
  layoutLineage,
  NODE_H,
  NODE_W,
} from "@/lib/lineage";
import { cn } from "@/lib/utils";

type State = "idle" | "selected" | "related" | "dim";
type ItemData = { node: LineageNode; state: State; onSelect: (id: string) => void };
type ItemNode = Node<ItemData, "item">;
type HeaderNode = Node<{ title: string }, "header">;

const HIDDEN = { opacity: 0, pointerEvents: "none" as const };
// Handles are invisible anchors; ids tell edges which side to use.
const HANDLES = [
  ["l", "target", Position.Left],
  ["r", "source", Position.Right],
  ["t", "target", Position.Top],
  ["b", "source", Position.Bottom],
  ["dt", "source", Position.Top],
  ["db", "target", Position.Bottom],
] as const;

function Item({ data }: NodeProps<ItemNode>) {
  const { node, state, onSelect } = data;
  const { icon: Icon, chip } = KIND_STYLE[node.kind];
  return (
    <>
      {HANDLES.map(([id, type, position]) => (
        <Handle
          key={id}
          id={id}
          type={type}
          position={position}
          isConnectable={false}
          style={HIDDEN}
        />
      ))}
      <button
        type="button"
        aria-pressed={state === "selected"}
        aria-label={`${KIND_LABEL[node.kind]}: ${node.label}`}
        onClick={() => onSelect(node.id)}
        title={node.label}
        style={{ width: NODE_W, height: NODE_H }}
        className={cn(
          "flex items-center gap-3 rounded-lg border bg-card px-3 text-left text-card-foreground transition-[opacity,border-color,box-shadow] hover:border-ring/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
          node.kind === "decision" && "border-dashed",
          state === "selected" && "border-primary ring-1 ring-primary",
          state === "related" && "border-primary/50",
          state === "dim" && "opacity-35",
        )}
      >
        <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-md", chip)}>
          <Icon className="size-4" />
        </span>
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className="line-clamp-2 text-sm leading-tight font-medium">{node.label}</span>
          {node.kind === "manuscript" ? (
            <span className="flex">
              <StatusBadge status={node.subtitle} />
            </span>
          ) : (
            <span
              className={cn(
                "truncate text-xs text-muted-foreground",
                node.kind === "analysis" && "font-mono",
              )}
            >
              {node.subtitle || " "}
            </span>
          )}
        </span>
      </button>
    </>
  );
}

function Header({ data }: NodeProps<HeaderNode>) {
  return (
    <h3
      style={{ width: NODE_W }}
      className="text-xs font-medium tracking-wide text-muted-foreground uppercase"
    >
      {data.title}
    </h3>
  );
}

const nodeTypes: NodeTypes = { item: Item, header: Header };

const stroke = (color: string, width: number, extra?: object) => ({
  stroke: color,
  strokeWidth: width,
  ...extra,
});

interface Props {
  data: Lineage;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function LineageGraph({ data, selectedId, onSelect }: Props) {
  const { nodes, edges } = useMemo(() => {
    const ix = indexLineage(data);
    const lit = selectedId && ix.byId.has(selectedId) ? highlightSet(ix, selectedId) : null;
    const layout = layoutLineage(data);
    const nodes: Node[] = [
      ...layout.headers.map<HeaderNode>((h) => ({
        id: h.id,
        type: "header",
        position: { x: h.x, y: h.y },
        data: { title: h.title },
        draggable: false,
        selectable: false,
        focusable: false,
      })),
      ...layout.nodes.map<ItemNode>((p) => {
        const node = ix.byId.get(p.id)!;
        const state: State = !lit
          ? "idle"
          : p.id === selectedId
            ? "selected"
            : lit.has(p.id)
              ? "related"
              : "dim";
        return {
          id: p.id,
          type: "item",
          position: { x: p.x, y: p.y },
          width: NODE_W,
          height: NODE_H,
          data: { node, state, onSelect },
          draggable: false,
          focusable: false,
        };
      }),
    ];
    const edges: Edge[] = data.edges.flatMap((e) => {
      const from = ix.byId.get(e.source);
      const to = ix.byId.get(e.target);
      if (!from || !to) return [];
      const on = !!lit && lit.has(e.source) && lit.has(e.target);
      const color = on ? "var(--primary)" : "var(--muted-foreground)";
      const opacity = !lit ? 0.55 : on ? 1 : 0.12;
      const base = { id: e.id, source: e.source, target: e.target, focusable: false };
      if (from.kind === "decision")
        return {
          ...base,
          sourceHandle: "dt",
          targetHandle: "db",
          style: stroke(color, 1.25, { strokeDasharray: "4 4", opacity }),
        };
      if (from.kind === "dataset" && to.kind === "dataset")
        return {
          ...base,
          sourceHandle: "b",
          targetHandle: "t",
          style: stroke(color, 1, { strokeDasharray: "1 4", strokeLinecap: "round", opacity }),
        };
      return {
        ...base,
        sourceHandle: "r",
        targetHandle: "l",
        style: stroke(color, on ? 2 : 1.5, { opacity }),
      };
    });
    return { nodes, edges };
  }, [data, selectedId, onSelect]);

  return (
    <div
      role="region"
      aria-label="Lineage graph. Use the list view for a text version."
      className="lineage-flow h-full w-full"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.04, maxZoom: 1 }}
        minZoom={0.2}
        maxZoom={1.5}
        nodesDraggable={false}
        nodesConnectable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        panOnScroll
        proOptions={{ hideAttribution: false }}
      >
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
