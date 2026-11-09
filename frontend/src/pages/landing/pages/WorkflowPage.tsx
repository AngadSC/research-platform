import { useState, type KeyboardEvent } from "react";
import {
  Check,
  CtaBand,
  Icon,
  ICONS,
  NextPages,
  PageHero,
  SectionHead,
  type Tone,
} from "../shared";

const STAGES: {
  label: string;
  tone: Tone;
  icon: string;
  title: string;
  body: string;
  record: string[];
  reminders: string;
  ai: string;
}[] = [
  {
    label: "Funding",
    tone: "amber",
    icon: ICONS.dollar,
    title: "Record what pays for the work",
    body: "Note each grant or award behind the project, and keep your institution's internal funding and grant-approval pages one click away.",
    record: [
      "Funder, award number and who holds it",
      "Start and end dates",
      "Status from applied to awarded, active and closed",
    ],
    reminders: "Funding ending in the next 90 days shows on the PI dashboard.",
    ai: "Ask your AI which projects run out of funding before the next term.",
  },
  {
    label: "Ethics",
    tone: "pink",
    icon: ICONS.shield,
    title: "Link the approvals that cover the study",
    body: "Keep each approval's number, board, dates and documents, and link it to every project it covers so renewals reach the right people.",
    record: [
      "Approval number, board and expiry date",
      "Attached approval letters and amendments",
      "Links to your ethics office and application system",
    ],
    reminders: "Reminders 60, 30 and 7 days before expiry, to the PI and project leads.",
    ai: "Ask which approvals expire this semester and which projects they cover.",
  },
  {
    label: "Participants",
    tone: "violet",
    icon: ICONS.users,
    title: "Track recruitment, not people",
    body: "Set a target and log dated counts as they change. Names and records stay in REDCap or your approved system, linked by title only.",
    record: [
      "Target enrolment and notes",
      "Screened, enrolled, withdrawn and completed counts",
      "A link to the REDCap project or Qualtrics survey",
    ],
    reminders: "Everyone sees how close the study is to its target.",
    ai: "Ask how recruitment is going against the target this month.",
  },
  {
    label: "Data",
    tone: "blue",
    icon: ICONS.archive,
    title: "Plan your data, then point to it",
    body: "Write the data management plan funders expect, then add a dataset record for each version, saying where it lives and who controls access.",
    record: [
      "A Tri-Agency style data management plan, approved by the lead",
      "Dataset name, location, version and checksum",
      "Links to Drive, OneDrive, Borealis, FRDR and more",
    ],
    reminders: "Projects without an approved plan are flagged on the dashboard.",
    ai: "Ask which dataset versions exist and where each one is stored.",
  },
  {
    label: "Analysis",
    tone: "teal",
    icon: ICONS.graph,
    title: "Say which code made which result",
    body: "An analysis records the code (repository and commit) and the dataset versions it ran on. A result is a finding, with figures, that came out of one analysis.",
    record: [
      "GitHub or GitLab repository and commit",
      "Datasets and versions used",
      "Results with figures and tables",
    ],
    reminders: "Linked files are checked daily, so you know when one changes.",
    ai: "Ask which analysis produced a figure, and on what data.",
  },
  {
    label: "Manuscript",
    tone: "green",
    icon: ICONS.doc,
    title: "Connect the paper to its results",
    body: "Link your manuscript on Overleaf or Google Docs and choose the results it reports, so every number in it can be traced back.",
    record: [
      "Link to the draft",
      "Status from drafting to published",
      "The results the paper uses",
    ],
    reminders: "The lineage graph updates as soon as you link a result.",
    ai: "Ask your AI to list every result in the draft and where it came from.",
  },
  {
    label: "Review",
    tone: "red",
    icon: ICONS.flag,
    title: "Get sign-off and write down decisions",
    body: "Ask a colleague to review or sign off on part of the project, and record the decisions the lab made along the way, with the reasons.",
    record: [
      "Review requests and where each one stands",
      "Decisions with supporting documents and papers",
      "Zotero references added to decisions",
    ],
    reminders: "Each request shows where it stands until it's approved.",
    ai: "Ask why the lab made a decision, with links to the evidence.",
  },
];

type NodeKind = "dataset" | "analysis" | "result" | "manuscript" | "decision";
const NODES: {
  id: string;
  kind: NodeKind;
  label: string;
  sub: string;
  x: number;
  y: number;
  from: string[];
}[] = [
  { id: "d1", kind: "dataset", label: "Survey export", sub: "v1", x: 10, y: 40, from: [] },
  { id: "d2", kind: "dataset", label: "Survey export", sub: "v2", x: 10, y: 200, from: [] },
  {
    id: "a1",
    kind: "analysis",
    label: "Descriptives",
    sub: "commit 8b21e0c",
    x: 240,
    y: 40,
    from: ["d1"],
  },
  {
    id: "a2",
    kind: "analysis",
    label: "Mixed model",
    sub: "commit 3f9c1a2",
    x: 240,
    y: 200,
    from: ["d2"],
  },
  {
    id: "x1",
    kind: "decision",
    label: "Exclude incomplete",
    sub: "decision",
    x: 240,
    y: 320,
    from: [],
  },
  {
    id: "r1",
    kind: "result",
    label: "Table 1",
    sub: "sample summary",
    x: 470,
    y: 40,
    from: ["a1"],
  },
  {
    id: "r2",
    kind: "result",
    label: "Exposure effect",
    sub: "Figure 2",
    x: 470,
    y: 200,
    from: ["a2", "x1"],
  },
  {
    id: "m1",
    kind: "manuscript",
    label: "Paper draft",
    sub: "Overleaf",
    x: 690,
    y: 120,
    from: ["r1", "r2"],
  },
];
const KIND_TONE: Record<NodeKind, Tone> = {
  dataset: "blue",
  analysis: "violet",
  result: "pink",
  manuscript: "green",
  decision: "amber",
};
const W = 205;
const H = 56;
const byId = Object.fromEntries(NODES.map((n) => [n.id, n]));

function upstream(id: string, acc = new Set<string>()) {
  acc.add(id);
  for (const f of byId[id]!.from) upstream(f, acc);
  return acc;
}

function LineageDemo() {
  const [sel, setSel] = useState("r2");
  const chain = upstream(sel);
  const ordered = NODES.filter((n) => chain.has(n.id)).sort((a, b) => a.x - b.x);
  const onKey = (e: KeyboardEvent, id: string) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setSel(id);
    }
  };
  return (
    <div className="lbp-lineage">
      <div className="lbp-lineage-graph">
        <svg viewBox="0 0 905 390" role="group" aria-label="Example lineage graph">
          {NODES.flatMap((n) =>
            n.from.map((f) => {
              const a = byId[f]!;
              const on = chain.has(n.id) && chain.has(f);
              const x1 = a.x + W;
              const y1 = a.y + H / 2;
              const x2 = n.x;
              const y2 = n.y + H / 2;
              const mx = (x1 + x2) / 2;
              return (
                <path
                  key={`${f}-${n.id}`}
                  d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}
                  className="lbp-edge"
                  data-on={on}
                />
              );
            }),
          )}
          {NODES.map((n) => (
            <g
              key={n.id}
              transform={`translate(${n.x},${n.y})`}
              className={`lbp-node lbp-tone-${KIND_TONE[n.kind]}`}
              data-on={chain.has(n.id)}
              data-sel={sel === n.id}
              role="button"
              tabIndex={0}
              aria-pressed={sel === n.id}
              aria-label={`${n.kind} ${n.label} ${n.sub}`}
              onClick={() => setSel(n.id)}
              onKeyDown={(e) => onKey(e, n.id)}
            >
              <rect width={W} height={H} rx={14} />
              <text x={14} y={23} className="lbp-node-kind">
                {n.kind}
              </text>
              <text x={14} y={43} className="lbp-node-label">
                {n.label} · {n.sub}
              </text>
            </g>
          ))}
        </svg>
      </div>
      <div className="lbp-lineage-panel" aria-live="polite">
        <p className="lbp-kicker">Traced back from {byId[sel]!.label}</p>
        <ol>
          {ordered.map((n) => (
            <li key={n.id} className={`lbp-tone-${KIND_TONE[n.kind]}`}>
              <span className="lbp-art-dot" />
              <span>
                <small>{n.kind}</small>
                <strong>
                  {n.label} · {n.sub}
                </strong>
              </span>
            </li>
          ))}
        </ol>
        <p className="lbp-small">Click any box in the graph to trace it back.</p>
      </div>
    </div>
  );
}

function Stepper() {
  const [i, setI] = useState(0);
  const s = STAGES[i]!;
  const pct = ((i + 1) / STAGES.length) * 100;
  return (
    <div className={`lbp-stepper lbp-tone-${s.tone}`}>
      <div className="lbp-progress lbp-progress-thick" aria-hidden="true">
        <span style={{ width: `${pct}%` }} />
      </div>
      <div role="tablist" aria-label="Workflow stages" className="lbp-stage-tabs">
        {STAGES.map((st, n) => (
          <button
            key={st.label}
            type="button"
            role="tab"
            id={`lbp-stage-${n}`}
            aria-controls="lbp-stage-panel"
            aria-selected={n === i}
            data-done={n < i}
            className={`lbp-tone-${st.tone}`}
            onClick={() => setI(n)}
          >
            <span className="lbp-stage-icon">
              <Icon d={st.icon} size={18} />
            </span>
            {st.label}
          </button>
        ))}
      </div>
      <div
        id="lbp-stage-panel"
        role="tabpanel"
        aria-labelledby={`lbp-stage-${i}`}
        className="lbp-stage-panel"
      >
        <div>
          <p className="lbp-kicker">
            Stage {i + 1} of {STAGES.length} · {s.label}
          </p>
          <h3 className="lb-h3">{s.title}</h3>
          <p className="lbp-body">{s.body}</p>
          <div className="lb-actions" style={{ marginTop: 24 }}>
            <button
              type="button"
              className="lbp-btn lbp-btn-soft"
              disabled={i === 0}
              onClick={() => setI(i - 1)}
            >
              ← Previous
            </button>
            <button
              type="button"
              className="lbp-btn lbp-btn-primary"
              disabled={i === STAGES.length - 1}
              onClick={() => setI(i + 1)}
            >
              Next stage →
            </button>
          </div>
        </div>
        <div className="lbp-stage-side">
          <p className="lbp-side-head">What you record</p>
          <ul className="lbp-ticks">
            {s.record.map((r) => (
              <li key={r}>
                <Check />
                {r}
              </li>
            ))}
          </ul>
          <div className="lbp-side-box">
            <Icon d={ICONS.bell} size={18} />
            <span>{s.reminders}</span>
          </div>
          <div className="lbp-side-box lbp-side-ai">
            <Icon d={ICONS.sparkle} size={18} />
            <span>{s.ai}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function WorkflowPage() {
  return (
    <>
      <PageHero
        theme="workflow"
        eyebrow="The research workflow"
        title="Every stage of a study, from funding to final paper."
        lead="Each project has a Workflow tab that follows the study through seven stages. Your institution's ethics, funding and data links appear where they apply, and everything links together as you go."
        secondary={{ to: "#lineage", label: "Try the lineage graph" }}
      />

      <section className="lb-wrap lb-section">
        <SectionHead
          eyebrow="Seven stages"
          title="Click through a study."
          lead="Each stage is a tab in every project. Here's what goes in each one."
        />
        <Stepper />
      </section>

      <section id="lineage" className="lbp-band lbp-band-workflow">
        <div className="lb-wrap lb-section">
          <SectionHead
            eyebrow="Lineage"
            title="Follow any result back to its data and code."
            lead="As you add datasets, analyses, results and manuscripts, labbenchos joins them into a graph. Click a box to see everything it came from."
          />
          <LineageDemo />
        </div>
      </section>

      <section className="lb-wrap lb-section">
        <SectionHead eyebrow="Why it matters" title="Answers in two clicks, years later." center />
        <div className="lbp-quotes">
          {[
            ["A reviewer asks", "“Which version of the data is Figure 2 based on?”"],
            ["A new student asks", "“Why did we exclude incomplete responses?”"],
            ["Your funder asks", "“Where is the data from this grant deposited?”"],
          ].map(([who, q]) => (
            <div key={who} className="lbp-quote-card">
              <small>{who}</small>
              <p>{q}</p>
              <span>
                <Icon d={ICONS.check} size={16} width={3} /> Answered from the record
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="lb-wrap" style={{ paddingBottom: 112 }}>
        <NextPages
          pages={[
            { to: "/features", title: "All features", body: "Everything else in labbenchos." },
            { to: "/for-labs", title: "For labs", body: "The PI dashboard, roles and handovers." },
            {
              to: "/for-institutions",
              title: "For institutions",
              body: "Data plans, ethics and security.",
            },
          ]}
        />
      </section>

      <CtaBand
        theme="workflow"
        title="Put your next study on labbenchos."
        body="Start with one project and see the whole workflow come together."
      />
    </>
  );
}
