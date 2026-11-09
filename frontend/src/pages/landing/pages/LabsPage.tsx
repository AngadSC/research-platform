import { useState } from "react";
import { Link } from "react-router";
import {
  Check,
  CtaBand,
  Faq,
  Icon,
  ICONS,
  NextPages,
  PageHero,
  SectionHead,
  Tile,
  type Tone,
} from "../shared";

const ROLES = [
  {
    id: "pi",
    label: "PI",
    blurb: "Runs the lab. Sees everything, decides who's in, and gets the reminders that matter.",
    can: [true, true, true, true, true, true],
  },
  {
    id: "admin",
    label: "Lab admin",
    blurb: "A lab manager or senior student who keeps the lab running day to day.",
    can: [true, true, true, true, true, true],
  },
  {
    id: "member",
    label: "Member",
    blurb: "Students, RAs and postdocs doing the research on the projects they're added to.",
    can: [true, true, false, false, false, false],
  },
  {
    id: "viewer",
    label: "Viewer",
    blurb: "Collaborators or committee members who need to read along without changing things.",
    can: [true, false, false, false, false, false],
  },
];
const ABILITIES = [
  "See the lab and the projects they're on",
  "Start projects and add to inventory, the calendar and papers",
  "Invite people and change roles",
  "See the lab dashboard",
  "Set required trainings and see everyone's records",
  "View the audit log",
];

const QUIET = [
  { key: "overdue", label: "Overdue tasks" },
  { key: "ethics", label: "Ethics to renew" },
  { key: "training", label: "Training expiring" },
  { key: "dmp", label: "No data plan" },
  { key: "stalled", label: "Stalled projects" },
  { key: "owner", label: "Need an owner" },
];
const BUSY: Record<string, { n: number; detail: string }> = {
  overdue: { n: 3, detail: "2 on Memory study, 1 on Pilot survey" },
  ethics: { n: 1, detail: "Pro00123456 expires in 25 days" },
  training: { n: 2, detail: "TCPS 2 CORE lapses for 2 members" },
  dmp: { n: 1, detail: "Pilot survey has no approved plan" },
  stalled: { n: 1, detail: "Bilingual narratives: no change in 34 days" },
  owner: { n: 2, detail: "Left unassigned when a student left" },
};

const OPS: { icon: string; title: string; body: string; tone: Tone }[] = [
  {
    icon: ICONS.box,
    title: "Inventory and orders",
    body: "Equipment, reagents and software licences with locations and due dates. Track orders, and stock updates once when they arrive. Export to CSV anytime.",
    tone: "amber",
  },
  {
    icon: ICONS.calendar,
    title: "One lab calendar",
    body: "Lab events alongside every task, deadline, ethics expiry, funding end and inventory date, showing each person only what they can access.",
    tone: "blue",
  },
  {
    icon: ICONS.cap,
    title: "Training compliance",
    body: "Set the trainings your lab requires, by role or project. See who's done what, verify certificates, and get a weekly digest.",
    tone: "pink",
  },
  {
    icon: ICONS.users,
    title: "Onboarding checklists",
    body: "A checklist for people joining and one for people leaving, ticked off per person, so nobody misses a key or a course.",
    tone: "violet",
  },
  {
    icon: ICONS.chat,
    title: "Lab chat",
    body: "A room for the whole lab plus one per project, with unread counts, so conversations live next to the work.",
    tone: "teal",
  },
  {
    icon: ICONS.book,
    title: "Paper library",
    body: "Your lab's reading list. Add a paper by DOI, attach the PDF and read it in the browser.",
    tone: "green",
  },
];

const PEOPLE = [
  {
    name: "Sam (MSc student)",
    items: [
      ["Open tasks", "4"],
      ["Documents they own", "7"],
      ["Datasets they control", "2"],
      ["Analyses they ran", "3"],
      ["Ethics approvals naming them", "1"],
      ["External links to relink", "5"],
    ],
  },
  {
    name: "Priya (RA)",
    items: [
      ["Open tasks", "2"],
      ["Documents they own", "3"],
      ["Datasets they control", "0"],
      ["Analyses they ran", "1"],
      ["Ethics approvals naming them", "0"],
      ["External links to relink", "1"],
    ],
  },
];

const FAQS = [
  {
    q: "How long does it take to set up a lab?",
    a: "Minutes. Create the lab, choose your institution so its ethics and funding links are added for you, then invite people by email. You can add projects and records as you go.",
  },
  {
    q: "Do we have to move our files?",
    a: "No. Keep files in Google Drive, OneDrive, Dropbox, GitHub or wherever they are, and link them to the project. labbenchos reads titles and modified dates, and tells you when a linked file changes or disappears.",
  },
  {
    q: "Is anything ever deleted automatically?",
    a: "No. Set a keep-until date on projects and documents and they show up in Retention review when it passes. You decide what happens to each one.",
  },
  {
    q: "Can we see who did what?",
    a: "Yes. The audit log records views of documents, downloads, exports, role changes and deletions, with who did it and when. PIs and lab admins can filter it by person and date.",
  },
  {
    q: "We have more than one lab. Does that work?",
    a: "Yes. One account can belong to several labs, and each lab's data is kept completely separate from the others.",
  },
];

function Permissions() {
  const [id, setId] = useState("pi");
  const role = ROLES.find((r) => r.id === id)!;
  return (
    <div className="lbp-perm">
      <div role="tablist" aria-label="Lab roles" className="lbp-seg">
        {ROLES.map((r) => (
          <button
            key={r.id}
            type="button"
            role="tab"
            aria-selected={r.id === id}
            aria-controls="lbp-perm-panel"
            id={`lbp-role-${r.id}`}
            onClick={() => setId(r.id)}
          >
            {r.label}
          </button>
        ))}
      </div>
      <div
        id="lbp-perm-panel"
        role="tabpanel"
        aria-labelledby={`lbp-role-${role.id}`}
        className="lbp-perm-panel"
      >
        <p className="lbp-body">{role.blurb}</p>
        <ul className="lbp-perm-list">
          {ABILITIES.map((a, n) => (
            <li key={a} data-ok={role.can[n]}>
              <Check ok={role.can[n]} />
              {a}
            </li>
          ))}
        </ul>
        <p className="lbp-small">
          Inside a project, people are also a Lead, Contributor or Viewer, so a student can lead
          their own thesis project and only read along on others.
        </p>
      </div>
    </div>
  );
}

function DashboardDemo() {
  const [busy, setBusy] = useState(false);
  return (
    <div className="lbp-demo">
      <div className="lbp-demo-bar">
        <div>
          <strong>Lab dashboard</strong>
          <span>{busy ? "A typical busy week" : "A quiet week"}</span>
        </div>
        <label className="lbp-switch">
          <input type="checkbox" checked={busy} onChange={(e) => setBusy(e.target.checked)} />
          <span aria-hidden="true" />
          Busy week
        </label>
      </div>
      {busy ? null : <p className="lbp-allclear">✓ All clear. Nothing needs you this week.</p>}
      <div className="lbp-dash">
        {QUIET.map((c) => {
          const b = BUSY[c.key]!;
          return (
            <div key={c.key} className="lbp-dash-card" data-alert={busy}>
              <span className="lbp-dash-label">{c.label}</span>
              <span className="lbp-dash-n">{busy ? b.n : 0}</span>
              <span className="lbp-dash-detail">{busy ? b.detail : "All clear"}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function HandoverDemo() {
  const [who, setWho] = useState(0);
  const [made, setMade] = useState(false);
  const p = PEOPLE[who]!;
  return (
    <div className="lbp-demo lbp-demo-light">
      <div className="lbp-demo-bar">
        <div>
          <strong>Handover report</strong>
          <span>Pick who&rsquo;s leaving, then generate.</span>
        </div>
      </div>
      <div className="lbp-seg lbp-seg-sm" role="group" aria-label="Departing member">
        {PEOPLE.map((x, n) => (
          <button
            key={x.name}
            type="button"
            aria-pressed={n === who}
            onClick={() => {
              setWho(n);
              setMade(false);
            }}
          >
            {x.name}
          </button>
        ))}
      </div>
      {!made ? (
        <button
          type="button"
          className="lbp-btn lbp-btn-primary"
          style={{ marginTop: 18 }}
          onClick={() => setMade(true)}
        >
          Generate handover
        </button>
      ) : (
        <ul className="lbp-handover" aria-live="polite">
          {p.items.map(([k, v], n) => (
            <li key={k} style={{ animationDelay: `${n * 70}ms` }}>
              <span>{k}</span>
              <strong>{v}</strong>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function LabsPage() {
  return (
    <>
      <PageHero
        theme="labs"
        eyebrow="For PIs and lab managers"
        title="See your whole lab at a glance, and stop chasing."
        lead="Projects, ethics, funding, training and inventory in one place, with reminders before anything lapses and a record of the work that stays when students move on."
        secondary={{ to: "#dashboard", label: "Try the dashboard" }}
        art={
          <div className="lbp-art-card">
            <p className="lbp-art-title">Needs attention</p>
            {[
              ["Ethics renewal in 25 days", "Memory study", "red"],
              ["2 trainings expiring", "TCPS 2 CORE", "amber"],
              ["Data plan approved", "Pilot survey", "green"],
            ].map(([t, s, c]) => (
              <div key={t} className={`lbp-art-row lbp-tone-${c}`}>
                <span className="lbp-art-dot" />
                <span>
                  <strong>{t}</strong>
                  <small>{s}</small>
                </span>
              </div>
            ))}
          </div>
        }
      />

      <section id="dashboard" className="lb-wrap lb-section">
        <div className="lbp-two">
          <div>
            <SectionHead
              eyebrow="The PI dashboard"
              title="What's late, what's due, and where nothing has moved."
              lead="Your dashboard pulls every project together: overdue tasks, approvals about to expire, funding ending, trainings lapsing, projects with no data plan and work with no owner. Flip the switch to see a busy week."
            />
            <ul className="lbp-ticks">
              <li>
                <Check /> Ethics reminders at 60, 30 and 7 days, to the PI and project leads
              </li>
              <li>
                <Check /> Funding ending in the next 90 days
              </li>
              <li>
                <Check /> Every person&rsquo;s open, overdue and recently finished tasks
              </li>
            </ul>
          </div>
          <DashboardDemo />
        </div>
      </section>

      <section className="lbp-band lbp-band-labs">
        <div className="lb-wrap lb-section">
          <SectionHead
            eyebrow="Roles and permissions"
            title="Everyone sees what they need, and nothing more."
            lead="Four lab roles, plus roles on each project. Pick one to see what it can do."
          />
          <Permissions />
        </div>
      </section>

      <section className="lb-wrap lb-section">
        <SectionHead
          eyebrow="Running the lab"
          title="Replace five spreadsheets with one place."
          lead="The day-to-day work of keeping a lab going, connected to the same people and projects."
        />
        <div className="lbp-tiles">
          {OPS.map((o) => (
            <Tile key={o.title} {...o} />
          ))}
        </div>
      </section>

      <section className="lbp-band lbp-band-dark">
        <div className="lb-wrap lb-section">
          <div className="lbp-two">
            <div>
              <SectionHead
                eyebrow="Continuity"
                title="When a student graduates, their work stays."
                lead="Generate a handover report for anyone leaving: everything they own or lead, and anything that would be left with no owner. Reassign items, then print it or keep it on file."
              />
              <ul className="lbp-ticks lbp-ticks-dark">
                <li>
                  <Check /> Tasks are unassigned automatically when someone loses access, and the
                  lead is told
                </li>
                <li>
                  <Check /> Integration connections are revoked when a member is removed
                </li>
                <li>
                  <Check /> Departing-member checklist, ticked off per person
                </li>
              </ul>
            </div>
            <HandoverDemo />
          </div>
        </div>
      </section>

      <section className="lb-wrap lb-section">
        <SectionHead
          eyebrow="Your research record"
          title="Trace any result back to its data and code."
          lead="Record datasets, analyses, results, decisions and manuscripts as you go. labbenchos links them into a lineage graph, so a reviewer's question takes two clicks to answer, years later."
        />
        <div className="lbp-strip">
          {[
            ["Dataset", "Survey export v2", "blue"],
            ["Analysis", "Mixed model · commit 3f9c1a2", "violet"],
            ["Result", "Effect of language exposure", "pink"],
            ["Manuscript", "Draft on Overleaf", "green"],
          ].map(([k, v, c], n, all) => (
            <div key={k} className="lbp-strip-item">
              <div className={`lbp-strip-node lbp-tone-${c}`}>
                <small>{k}</small>
                <strong>{v}</strong>
              </div>
              {n < all.length - 1 && (
                <span className="lbp-strip-arrow" aria-hidden="true">
                  <Icon d={ICONS.arrow} size={22} />
                </span>
              )}
            </div>
          ))}
        </div>
        <p className="lbp-small" style={{ marginTop: 18 }}>
          See it working, step by step, on the <Link to="/workflow#lineage">Workflow page</Link>.
        </p>
      </section>

      <section className="lbp-band lbp-band-soft">
        <div className="lb-wrap lb-section">
          <SectionHead eyebrow="Questions" title="What PIs ask before signing up." center />
          <Faq items={FAQS} />
        </div>
      </section>

      <section className="lb-wrap lb-section">
        <NextPages
          pages={[
            {
              to: "/for-students",
              title: "For your students",
              body: "How labbenchos helps new lab members get going.",
            },
            {
              to: "/for-institutions",
              title: "Security and compliance",
              body: "What your research office will ask about.",
            },
            { to: "/pricing", title: "Pricing", body: "Find the plan that fits your lab." },
          ]}
        />
      </section>

      <CtaBand
        theme="labs"
        title="See your lab in labbenchos."
        body="Tell us about your lab and we'll set you up and walk you through it."
      />
    </>
  );
}
