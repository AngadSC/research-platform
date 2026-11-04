import { describe, expect, it } from "vitest";
import { COMMIT, sample } from "@/lib/lineage.fixture";
import {
  decisionsFor,
  highlightSet,
  indexLineage,
  layoutLineage,
  recordPath,
  safeHttpUrl,
  upstreamChain,
  usedBy,
} from "@/lib/lineage";

const at = (id: string) => layoutLineage(sample).nodes.find((p) => p.id === id)!;

describe("layoutLineage", () => {
  it("puts each kind in its own column, left to right, and decisions in a lane below", () => {
    const col = (id: string) => at(id).column;
    expect(["dataset:d1", "analysis:a1", "result:r1", "manuscript:m1"].map(col)).toEqual([
      0, 1, 2, 3,
    ]);
    expect(at("decision:x1").lane).toBe(true);
    expect(at("decision:x1").y).toBeGreaterThan(
      Math.max(...["dataset:d1", "dataset:d2", "result:r2"].map((i) => at(i).y)),
    );
    expect(at("decision:x1").column).toBe(1); // under the analysis it applies to
    expect(at("analysis:a1").x).toBeGreaterThan(at("dataset:d1").x);
  });

  it("stacks dataset versions so the previous version sits directly above", () => {
    expect(at("dataset:d1").x).toBe(at("dataset:d2").x);
    expect(at("dataset:d2").y).toBeGreaterThan(at("dataset:d1").y);
  });

  it("orders by barycenter: the result in the manuscript moves next to it, and it is deterministic", () => {
    // r2 arrives first in the data but r1 feeds the manuscript; both share one analysis, so ties keep input order.
    expect(layoutLineage(sample)).toEqual(layoutLineage(structuredClone(sample)));
    const crossing = {
      nodes: [
        ...["a", "b"].map((k) => ({
          id: `dataset:${k}`,
          kind: "dataset" as const,
          label: k,
          subtitle: "",
          href_id: k,
          meta: {},
        })),
        ...["x", "y"].map((k) => ({
          id: `analysis:${k}`,
          kind: "analysis" as const,
          label: k,
          subtitle: "",
          href_id: k,
          meta: {},
        })),
      ],
      // a feeds y, b feeds x: input order would cross, so analyses must swap.
      edges: [
        { id: "1", source: "dataset:a", target: "analysis:y", kind: "dataset" as const },
        { id: "2", source: "dataset:b", target: "analysis:x", kind: "dataset" as const },
      ],
    };
    const y = (id: string) => layoutLineage(crossing).nodes.find((p) => p.id === id)!.y;
    expect(y("analysis:y")).toBeLessThan(y("analysis:x"));
  });
});

describe("chains", () => {
  const ix = indexLineage(sample);

  it("walks a manuscript back to the dataset version and the commit", () => {
    const chain = upstreamChain(ix, "manuscript:m1")!;
    const result = chain.children[0]!;
    const analysis = result.children[0]!;
    const dataset = analysis.children[0]!;
    expect(result.node.id).toBe("result:r1");
    expect(analysis.node.meta.code_commit).toBe(COMMIT);
    expect(dataset.node.meta.version_label).toBe("v2");
    expect(dataset.node.meta.checksum).toBe("sha256-bbb");
    expect(dataset.children[0]!.node.meta.version_label).toBe("v1"); // previous version
  });

  it("finds downstream items, decisions and the highlighted path", () => {
    expect(usedBy(ix, "dataset:d1").map((x) => x.id)).toEqual([
      "dataset:d2",
      "analysis:a1",
      "result:r1",
      "result:r2",
      "manuscript:m1",
    ]);
    expect(decisionsFor(ix, "result:r1").map((d) => d.decision.id)).toEqual(["decision:x1"]);
    expect([...highlightSet(ix, "result:r2")].sort()).toEqual(
      ["dataset:d1", "dataset:d2", "analysis:a1", "result:r2", "decision:x1"].sort(),
    );
  });

  it("survives a cycle", () => {
    const loop = indexLineage({
      nodes: sample.nodes,
      edges: [
        ...sample.edges,
        { id: "c", source: "manuscript:m1", target: "dataset:d1", kind: "result" },
      ],
    });
    expect(upstreamChain(loop, "manuscript:m1")).not.toBeNull();
  });
});

describe("helpers", () => {
  it("links only http and https", () => {
    expect(safeHttpUrl("https://a.org/x")).toBe("https://a.org/x");
    expect(safeHttpUrl("javascript:alert(1)")).toBeNull();
    expect(safeHttpUrl("not a url")).toBeNull();
  });
  it("builds record paths", () => {
    expect(recordPath({ kind: "analysis", href_id: "u" })).toBe("research/analyses/u");
  });
});
