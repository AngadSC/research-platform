// Pure lineage logic (D13 layout, D44 chains). No React, no React Flow.
import type { Lineage, LineageKind, LineageNode } from "@/lib/api-types";

export const COLUMN_KINDS = ["dataset", "analysis", "result", "manuscript"] as const;
export const COLUMN_TITLES: Record<string, string> = {
  dataset: "Datasets",
  analysis: "Analyses",
  result: "Results",
  manuscript: "Manuscripts",
  decision: "Decisions",
};
export const KIND_LABEL: Record<LineageKind, string> = {
  dataset: "Dataset",
  analysis: "Analysis",
  result: "Result",
  manuscript: "Manuscript",
  decision: "Decision",
};
const PLURAL: Record<LineageKind, string> = {
  dataset: "datasets",
  analysis: "analyses",
  result: "results",
  manuscript: "manuscripts",
  decision: "decisions",
};
/** Route below the project for a node's full record. */
export const recordPath = (n: Pick<LineageNode, "kind" | "href_id">) =>
  `research/${PLURAL[n.kind]}/${n.href_id}`;

export const NODE_W = 232;
export const NODE_H = 68;
const COL_GAP = 88;
const ROW_GAP = 20;
const HEADER_H = 44;
const LANE_GAP = 40;

/** Column index for a kind, or -1 for decisions (they sit in the lane below). */
export const columnOf = (kind: LineageKind) => COLUMN_KINDS.indexOf(kind as never);

export interface Placed {
  id: string;
  x: number;
  y: number;
  column: number;
  lane: boolean;
}
export interface Header {
  id: string;
  title: string;
  x: number;
  y: number;
}
export interface Layout {
  nodes: Placed[];
  headers: Header[];
}

// ---------------------------------------------------------------------------
// Graph index

export interface Index {
  byId: Map<string, LineageNode>;
  /** Flow edges only (decision links excluded): target -> sources and source -> targets. */
  up: Map<string, string[]>;
  down: Map<string, string[]>;
  /** decision id -> what it applies to, and node id -> decisions attached to it. */
  applies: Map<string, string[]>;
  decisionsOf: Map<string, string[]>;
}

const push = (m: Map<string, string[]>, k: string, v: string) => {
  const list = m.get(k);
  if (list) {
    if (!list.includes(v)) list.push(v);
  } else m.set(k, [v]);
};

export function indexLineage(data: Lineage): Index {
  const byId = new Map(data.nodes.map((n) => [n.id, n]));
  const ix: Index = {
    byId,
    up: new Map(),
    down: new Map(),
    applies: new Map(),
    decisionsOf: new Map(),
  };
  for (const e of data.edges) {
    if (!byId.has(e.source) || !byId.has(e.target)) continue;
    if (byId.get(e.source)!.kind === "decision") {
      push(ix.applies, e.source, e.target);
      push(ix.decisionsOf, e.target, e.source);
    } else {
      push(ix.up, e.target, e.source);
      push(ix.down, e.source, e.target);
    }
  }
  return ix;
}

// ---------------------------------------------------------------------------
// Layout

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

/** Barycenter key: mean position of already-placed neighbours, else the node's own slot. */
function barycenter(ids: string[], pos: Map<string, number>, nbrs: (id: string) => string[]) {
  const key = new Map<string, number>();
  ids.forEach((id, i) => {
    const ps = nbrs(id).flatMap((n) => (pos.has(n) ? [pos.get(n)!] : []));
    key.set(id, ps.length ? mean(ps) : i);
  });
  return key;
}
const order = (ids: string[], key: Map<string, number>) =>
  // Array.prototype.sort is stable, so ties keep input order: the result is deterministic.
  [...ids].sort((a, b) => key.get(a)! - key.get(b)!);
const positions = (ids: string[]) => new Map(ids.map((id, i) => [id, i]));

/** Version chains root-first, so "previous version" always sits directly above its successor. */
function datasetChains(ids: string[], ix: Index): string[][] {
  const set = new Set(ids);
  const prev = new Map<string, string[]>();
  const next = new Map<string, string[]>();
  for (const id of ids)
    for (const p of ix.up.get(id) ?? []) {
      if (!set.has(p)) continue;
      push(prev, id, p);
      push(next, p, id);
    }
  const seen = new Set<string>();
  const chains: string[][] = [];
  const walk = (id: string, chain: string[]) => {
    if (seen.has(id)) return;
    seen.add(id);
    chain.push(id);
    for (const n of next.get(id) ?? []) walk(n, chain);
  };
  for (const id of ids)
    if (!prev.has(id)) {
      const chain: string[] = [];
      walk(id, chain);
      chains.push(chain);
    }
  for (const id of ids) if (!seen.has(id)) chains.push([id]); // cycles: defensive
  return chains;
}

// ponytail: one forward / backward / forward sweep, not iterated to convergence. Fine for
// project-sized graphs; iterate the sweeps if crossings ever look bad on large ones.
export function layoutLineage(data: Lineage): Layout {
  const ix = indexLineage(data);
  const ids = (kind: LineageKind) => data.nodes.filter((n) => n.kind === kind).map((n) => n.id);
  const dsIds = ids("dataset");
  let chains = datasetChains(dsIds, ix);
  let datasets = chains.flat();
  let analyses = ids("analysis");
  let results = ids("result");
  let manuscripts = ids("manuscript");

  const sortChains = (pos: Map<string, number>) => {
    const key = chains.map((c, i) => {
      const ps = c.flatMap((d) => (ix.down.get(d) ?? []).flatMap((a) => pos.get(a) ?? []));
      return ps.length ? mean(ps) : i;
    });
    chains = chains
      .map((c, i) => [c, key[i]!] as const)
      .sort((a, b) => a[1] - b[1])
      .map(([c]) => c);
    datasets = chains.flat();
  };

  const forward = () => {
    analyses = order(
      analyses,
      barycenter(analyses, positions(datasets), (id) => ix.up.get(id) ?? []),
    );
    results = order(
      results,
      barycenter(results, positions(analyses), (id) => ix.up.get(id) ?? []),
    );
    manuscripts = order(
      manuscripts,
      barycenter(manuscripts, positions(results), (id) => ix.up.get(id) ?? []),
    );
  };
  forward();
  sortChains(positions(analyses));
  forward();

  const nodes: Placed[] = [];
  const cols = [datasets, analyses, results, manuscripts];
  const x = (c: number) => c * (NODE_W + COL_GAP);
  const y = (r: number) => HEADER_H + r * (NODE_H + ROW_GAP);
  const placed = new Map<string, Placed>();
  cols.forEach((col, c) =>
    col.forEach((id, r) => {
      const p = { id, x: x(c), y: y(r), column: c, lane: false };
      nodes.push(p);
      placed.set(id, p);
    }),
  );

  // Decisions: a lane below, each under the column of the first thing it applies to.
  const decisions = ids("decision");
  const laneTop = y(Math.max(0, ...cols.map((c) => c.length))) + LANE_GAP + HEADER_H;
  const slot = new Map<number, number>();
  const targetY = new Map(
    decisions.map((d) => {
      const ys = (ix.applies.get(d) ?? []).map((t) => placed.get(t)?.y ?? 0);
      return [d, ys.length ? mean(ys) : 0];
    }),
  );
  for (const d of order(decisions, targetY)) {
    const first = (ix.applies.get(d) ?? []).map((t) => placed.get(t)).find(Boolean);
    const c = first?.column ?? 0;
    const k = slot.get(c) ?? 0;
    slot.set(c, k + 1);
    nodes.push({ id: d, x: x(c), y: laneTop + k * (NODE_H + ROW_GAP), column: c, lane: true });
  }

  const headers: Header[] = COLUMN_KINDS.map((k, c) => ({
    id: `header:${k}`,
    title: COLUMN_TITLES[k]!,
    x: x(c),
    y: 0,
  }));
  if (decisions.length)
    headers.push({
      id: "header:decision",
      title: COLUMN_TITLES.decision!,
      x: 0,
      y: laneTop - HEADER_H,
    });
  return { nodes, headers };
}

// ---------------------------------------------------------------------------
// Chains and highlighting

export interface ChainNode {
  node: LineageNode;
  children: ChainNode[];
}

/** Everything upstream of `id`, as a tree walking edges back to the source. */
export function upstreamChain(ix: Index, id: string, path: string[] = []): ChainNode | null {
  const node = ix.byId.get(id);
  if (!node) return null;
  const here = [...path, id];
  const children = (ix.up.get(id) ?? [])
    .filter((p) => !here.includes(p)) // cycle guard
    .flatMap((p) => upstreamChain(ix, p, here) ?? []);
  return { node, children };
}

function reach(map: Map<string, string[]>, id: string): string[] {
  const out: string[] = [];
  const seen = new Set([id]);
  const stack = [id];
  while (stack.length) {
    for (const n of map.get(stack.pop()!) ?? [])
      if (!seen.has(n)) {
        seen.add(n);
        out.push(n);
        stack.push(n);
      }
  }
  return out;
}

/** Transitive downstream nodes, left to right by column. */
export function usedBy(ix: Index, id: string): LineageNode[] {
  return reach(ix.down, id)
    .flatMap((d) => ix.byId.get(d) ?? [])
    .sort((a, b) => columnOf(a.kind) - columnOf(b.kind));
}

export interface AppliedDecision {
  decision: LineageNode;
  appliesTo: LineageNode[];
}
/** Decisions attached to this node or anything upstream of it; for a decision, nothing. */
export function decisionsFor(ix: Index, id: string): AppliedDecision[] {
  const scope = new Set([id, ...reach(ix.up, id)]);
  const out = new Map<string, AppliedDecision>();
  for (const s of scope)
    for (const d of ix.decisionsOf.get(s) ?? []) {
      const decision = ix.byId.get(d);
      if (!decision) continue;
      const entry = out.get(d) ?? { decision, appliesTo: [] };
      entry.appliesTo.push(ix.byId.get(s)!);
      out.set(d, entry);
    }
  return [...out.values()];
}

/** Ids lit up when `id` is selected: itself, the full path either side, and the decisions that apply. */
export function highlightSet(ix: Index, id: string): Set<string> {
  if (ix.byId.get(id)?.kind === "decision") return new Set([id, ...(ix.applies.get(id) ?? [])]);
  return new Set([
    id,
    ...reach(ix.up, id),
    ...reach(ix.down, id),
    ...decisionsFor(ix, id).map((d) => d.decision.id),
  ]);
}

// ---------------------------------------------------------------------------
// Metadata helpers

export function metaStr(n: LineageNode, key: string): string {
  const v = n.meta[key];
  return typeof v === "string" ? v : "";
}

/** Only http(s) URLs are ever linked; anything else (javascript:, data:) is dropped. */
export function safeHttpUrl(value: string): string | null {
  try {
    const u = new URL(value);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}
