import { describe, expect, it } from "vitest";
import { COMMIT, sample } from "@/lib/lineage.fixture";
import type { Lineage } from "@/lib/api-types";
import {
  decisionsFor,
  highlightSet,
  indexLineage,
  layoutLineage,
  recordGaps,
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
    expect(recordPath({ kind: "analysis", href_id: "u" })).toBe("workflow/analysis/analyses/u");
  });
});

describe("recordGaps", () => {
  const gapsOf = (d: Lineage) => recordGaps(d, indexLineage(d));
  /** The sample with where-it-is-kept written down for both datasets: nothing to flag. */
  const complete = (): Lineage => {
    const d = structuredClone(sample);
    for (const n of d.nodes) if (n.kind === "dataset") n.meta.location_text = "Shared drive";
    return d;
  };
  const edit = (d: Lineage, id: string, meta: Record<string, unknown>) => {
    const n = d.nodes.find((x) => x.id === id)!;
    n.meta = { ...n.meta, ...meta };
  };

  it("is empty for a complete record", () => {
    expect(gapsOf(complete())).toEqual([]);
  });

  it("flags a dataset with no location, but not one with a url or text", () => {
    const d = complete();
    edit(d, "dataset:d1", { location_text: "" });
    expect(gapsOf(d).map((g) => g.nodeId)).toEqual(["dataset:d1"]);
    edit(d, "dataset:d1", { location_url: "https://example.org/d1" });
    expect(gapsOf(d)).toEqual([]);
  });

  it("flags an analysis with no dataset", () => {
    const d = complete();
    d.edges = d.edges.filter((e) => e.id !== "dataset:d2>analysis:a1");
    const g = gapsOf(d);
    expect(g).toHaveLength(1);
    expect(g[0]).toMatchObject({ nodeId: "analysis:a1", info: false });
    expect(g[0]!.problem).toMatch(/No dataset is linked/);
  });

  it("flags missing code, and a repo without a commit, but accepts a code file", () => {
    const d = complete();
    edit(d, "analysis:a1", { code_commit: "", code_repo_url: "" });
    expect(gapsOf(d)[0]!.problem).toBe("No code commit or file is recorded.");
    edit(d, "analysis:a1", { code_repo_url: "https://github.com/lab/gut" });
    expect(gapsOf(d)[0]!.problem).toBe("The code repository is linked but not the exact commit.");
    edit(d, "analysis:a1", { code_attachment_id: "att1" });
    expect(gapsOf(d)).toEqual([]);
  });

  it("notes, neutrally, an analysis that uses a dataset version with a newer one", () => {
    const d = complete();
    d.edges = d.edges.map((e) =>
      e.id === "dataset:d2>analysis:a1" ? { ...e, id: "x", source: "dataset:d1" } : e,
    );
    expect(gapsOf(d)).toEqual([
      {
        nodeId: "analysis:a1",
        kind: "analysis",
        title: "Microbiome run",
        problem: "Uses Gut samples v1; a newer version v2 exists.",
        info: true,
      },
    ]);
  });

  it("flags a manuscript with no results, and does not nag about checksums or unused results", () => {
    const d = complete();
    d.edges = d.edges.filter((e) => e.target !== "manuscript:m1");
    edit(d, "dataset:d1", { checksum: "" });
    expect(gapsOf(d).map((g) => g.problem)).toEqual(["No results are linked to this manuscript."]);
  });

  it("sorts by column, then title", () => {
    const d = structuredClone(sample); // d1 and d2 both lack a location
    edit(d, "manuscript:m1", {});
    d.edges = d.edges.filter((e) => e.target !== "manuscript:m1");
    edit(d, "analysis:a1", { code_commit: "" });
    d.nodes.find((n) => n.id === "dataset:d1")!.label = "Zeta";
    expect(gapsOf(d).map((g) => g.nodeId)).toEqual([
      "dataset:d2",
      "dataset:d1",
      "analysis:a1",
      "manuscript:m1",
    ]);
  });
});
