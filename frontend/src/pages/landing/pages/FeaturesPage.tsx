import { useState } from "react";
import { CtaBand, Icon, ICONS, NextPages, PageHero, SectionHead, type Tone } from "../shared";

type Cat = "work" | "record" | "comply" | "lab" | "ai" | "trust";
const CATS: { id: Cat | "all"; label: string; tone: Tone }[] = [
  { id: "all", label: "Everything", tone: "green" },
  { id: "work", label: "Projects and tasks", tone: "blue" },
  { id: "record", label: "Research record", tone: "violet" },
  { id: "comply", label: "Ethics and compliance", tone: "pink" },
  { id: "lab", label: "Running the lab", tone: "amber" },
  { id: "ai", label: "AI", tone: "teal" },
  { id: "trust", label: "Security", tone: "red" },
];
const TONE = Object.fromEntries(CATS.map((c) => [c.id, c.tone])) as Record<Cat, Tone>;

const FEATURES: { cat: Cat; icon: string; title: string; body: string; details: string[] }[] = [
  {
    cat: "work",
    icon: ICONS.folder,
    title: "Projects",
    body: "A home for each study, with its description, status, people, deadlines and keep-until date.",
    details: [
      "Statuses from planning to archived",
      "Leads, contributors and viewers per project",
      "Deadlines with high, medium or low priority",
      "Export a whole project when you need it",
    ],
  },
  {
    cat: "work",
    icon: ICONS.tasks,
    title: "Tasks",
    body: "A board and a list for every project. Open a task to see its documents, files and discussion.",
    details: [
      "Assignee, status and due date",
      "Comment thread with notifications to the assignee",
      "Attach documents and files to a task",
      "Board or list, whichever you prefer by default",
    ],
  },
  {
    cat: "work",
    icon: ICONS.doc,
    title: "Documents",
    body: "Notes, protocols and write-ups in a clean block editor, with every version kept.",
    details: [
      "Every save keeps a revision you can view or restore",
      "Warns you if someone else saved while you were editing",
      "Keep-until dates for retention",
    ],
  },
  {
    cat: "work",
    icon: ICONS.box,
    title: "Files and PDFs",
    body: "Upload anonymized or aggregate files, or link them from where they already live. PDFs open in the browser.",
    details: [
      "Link from Google Drive, OneDrive, Dropbox, GitHub and more",
      "Told when a linked file changes or disappears",
      "Downloads always go through a permission check",
    ],
  },
  {
    cat: "work",
    icon: ICONS.calendar,
    title: "Lab calendar",
    body: "Lab events alongside every task, deadline, ethics expiry, funding end and inventory date.",
    details: ["Each person sees only what they can access", "Add lab events like meetings"],
  },
  {
    cat: "work",
    icon: ICONS.chat,
    title: "Lab and project chat",
    body: "A room for the whole lab and one for each project, with unread badges.",
    details: [
      "Conversations stay next to the work",
      "A reminder not to share participant identifiers",
    ],
  },
  {
    cat: "work",
    icon: ICONS.search,
    title: "Search everything",
    body: "Ctrl or Cmd + K searches projects, tasks, documents, research records, ethics approvals and links.",
    details: ["Jump to any page or action", "Results respect everyone's permissions"],
  },
  {
    cat: "record",
    icon: ICONS.graph,
    title: "Lineage graph",
    body: "See how datasets feed analyses, analyses produce results, and results end up in manuscripts.",
    details: [
      "Trace any result to its exact dataset version and code commit",
      "Decisions attached where they apply",
      "Graph and list views",
    ],
  },
  {
    cat: "record",
    icon: ICONS.archive,
    title: "Datasets, analyses and results",
    body: "Records that point to where data lives and say which code, on which versions, produced each finding.",
    details: [
      "Dataset: location, who controls access, version, checksum",
      "Analysis: repository and commit, datasets used, who ran it",
      "Result: summary with figures and tables",
    ],
  },
  {
    cat: "record",
    icon: ICONS.flag,
    title: "Decisions and review",
    body: "Note the choices the lab made and why, and ask colleagues to review or sign off on parts of a project.",
    details: ["Link supporting documents and papers", "Track where each review request stands"],
  },
  {
    cat: "record",
    icon: ICONS.doc,
    title: "Manuscripts",
    body: "Link your paper on Overleaf or Google Docs, and the results it uses.",
    details: ["Status from draft to published", "Results link back through the lineage"],
  },
  {
    cat: "record",
    icon: ICONS.book,
    title: "Paper library",
    body: "Your lab's reading list. Look up a paper by DOI, attach the PDF and read it in place.",
    details: ["Details filled in from the DOI", "References can be added to decisions"],
  },
  {
    cat: "comply",
    icon: ICONS.shield,
    title: "Ethics approvals",
    body: "Approval numbers, boards, linked projects, expiry dates and documents, for the whole lab.",
    details: [
      "Reminders 60, 30 and 7 days before expiry",
      "Sent to the PI and project leads",
      "Restricted approvals for sensitive projects",
    ],
  },
  {
    cat: "comply",
    icon: ICONS.dollar,
    title: "Funding",
    body: "Record the grants behind each project: funder, award number, dates and who holds it.",
    details: [
      "Funding ending soon shows on the dashboard",
      "Your institution's funding links in place",
    ],
  },
  {
    cat: "comply",
    icon: ICONS.doc,
    title: "Data management plans",
    body: "A DMP for each project, following the Tri-Agency RDM Policy and the Portage template.",
    details: ["Lead approval and full history", "Dashboard flags projects without one"],
  },
  {
    cat: "comply",
    icon: ICONS.users,
    title: "Participants",
    body: "Recruitment targets and a dated log of screened, enrolled, withdrawn and completed counts.",
    details: ["Counts only, never names", "Link the REDCap project or Qualtrics survey"],
  },
  {
    cat: "comply",
    icon: ICONS.archive,
    title: "Retention review",
    body: "Items past their keep-until date are listed for the PI. Nothing is ever deleted automatically.",
    details: ["Checked daily", "You decide what to keep"],
  },
  {
    cat: "lab",
    icon: ICONS.bell,
    title: "PI dashboard",
    body: "What's late, what's due soon and where nothing has moved, across every project and person.",
    details: [
      "Overdue tasks, expiring ethics, funding ending",
      "Stalled projects and work with no owner",
      "Per-person task counts",
    ],
  },
  {
    cat: "lab",
    icon: ICONS.cap,
    title: "Training records",
    body: "Required trainings by role or project, private records with certificates, and reminders.",
    details: ["PIs and admins verify completions", "Weekly digest for PIs"],
  },
  {
    cat: "lab",
    icon: ICONS.box,
    title: "Inventory and orders",
    body: "Equipment, reagents, consumables and licences, with locations, due dates and orders.",
    details: ["Receiving an order adds to stock once", "Search, filter and export to CSV"],
  },
  {
    cat: "lab",
    icon: ICONS.handover,
    title: "Handover and onboarding",
    body: "Checklists for people joining and leaving, and a report of everything a departing member owns.",
    details: ["Reassign items before they leave", "Printable report"],
  },
  {
    cat: "ai",
    icon: ICONS.sparkle,
    title: "Built-in assistant",
    body: "Chat with Claude or ChatGPT about your lab's records, using your own API key.",
    details: ["Usage billed to your own provider account", "Asks before saving any change"],
  },
  {
    cat: "ai",
    icon: ICONS.link,
    title: "Connect your AI app",
    body: "Add labbenchos as a connector in Claude, ChatGPT or any MCP app, or use an access token with tools like Claude Code.",
    details: ["Read-only or read and write", "Choose which labs each connection can see"],
  },
  {
    cat: "ai",
    icon: ICONS.shield,
    title: "Lab AI policy",
    body: "Each lab chooses: AI app and assistant, AI app only, or off.",
    details: ["Every connection listed and removable at once"],
  },
  {
    cat: "trust",
    icon: ICONS.eye,
    title: "Audit log",
    body: "Who viewed, downloaded, exported, changed or deleted what, and when.",
    details: ["Append-only", "Filter by person, action and date"],
  },
  {
    cat: "trust",
    icon: ICONS.key,
    title: "Sign-in and SSO",
    body: "Email and password, Google, or university SSO, with two-step verification.",
    details: ["SAML single sign-on for institutions", "Option to require SSO"],
  },
  {
    cat: "trust",
    icon: ICONS.lock,
    title: "Lab separation",
    body: "Every lab's data is kept apart, and every action is checked against your role.",
    details: ["Tested against every role on every endpoint"],
  },
];

const INTEGRATIONS: { group: string; tone: Tone; items: string[] }[] = [
  {
    group: "File storage",
    tone: "blue",
    items: ["Google Drive", "OneDrive and SharePoint", "Dropbox", "Box"],
  },
  { group: "Code", tone: "violet", items: ["GitHub", "GitLab"] },
  { group: "Writing", tone: "green", items: ["Overleaf"] },
  { group: "References", tone: "pink", items: ["Zotero"] },
  {
    group: "Repositories",
    tone: "teal",
    items: ["Zenodo", "Figshare", "Open Science Framework", "Borealis", "FRDR"],
  },
  { group: "Data capture", tone: "amber", items: ["REDCap", "Qualtrics"] },
  { group: "Protocols", tone: "red", items: ["protocols.io"] },
];

function Catalog() {
  const [cat, setCat] = useState<Cat | "all">("all");
  const [open, setOpen] = useState<string | null>(null);
  const shown = FEATURES.filter((f) => cat === "all" || f.cat === cat);
  return (
    <>
      <div className="lbp-filters" role="group" aria-label="Filter features">
        {CATS.map((c) => (
          <button
            key={c.id}
            type="button"
            aria-pressed={c.id === cat}
            className={`lbp-filter lbp-tone-${c.tone}`}
            onClick={() => {
              setCat(c.id);
              setOpen(null);
            }}
          >
            {c.label}
            <span>
              {c.id === "all" ? FEATURES.length : FEATURES.filter((f) => f.cat === c.id).length}
            </span>
          </button>
        ))}
      </div>
      <p className="lbp-small" aria-live="polite" style={{ marginTop: 16 }}>
        Showing {shown.length} features. Click one for details.
      </p>
      <div className="lbp-catalog">
        {shown.map((f) => {
          const isOpen = open === f.title;
          return (
            <button
              key={f.title}
              type="button"
              aria-expanded={isOpen}
              className={`lbp-feature lbp-tone-${TONE[f.cat]}`}
              data-open={isOpen}
              onClick={() => setOpen(isOpen ? null : f.title)}
            >
              <span className="lbp-tile-icon">
                <Icon d={f.icon} size={22} />
              </span>
              <strong>{f.title}</strong>
              <span className="lbp-feature-body">{f.body}</span>
              {isOpen && (
                <span className="lbp-feature-more">
                  {f.details.map((d) => (
                    <span key={d}>
                      <Icon d={ICONS.check} size={14} width={3} /> {d}
                    </span>
                  ))}
                </span>
              )}
              <span className="lbp-feature-toggle" aria-hidden="true">
                {isOpen ? "−" : "+"}
              </span>
            </button>
          );
        })}
      </div>
    </>
  );
}

function IntegrationWall() {
  const [group, setGroup] = useState<string | null>(null);
  return (
    <div className="lbp-int">
      <div className="lbp-filters" role="group" aria-label="Integration type">
        <button
          type="button"
          aria-pressed={group === null}
          className="lbp-filter lbp-tone-green"
          onClick={() => setGroup(null)}
        >
          All
        </button>
        {INTEGRATIONS.map((g) => (
          <button
            key={g.group}
            type="button"
            aria-pressed={group === g.group}
            className={`lbp-filter lbp-tone-${g.tone}`}
            onClick={() => setGroup(g.group)}
          >
            {g.group}
          </button>
        ))}
      </div>
      <div className="lbp-int-grid">
        {INTEGRATIONS.filter((g) => !group || g.group === group).flatMap((g) =>
          g.items.map((i) => (
            <div key={i} className={`lbp-int-item lbp-tone-${g.tone}`}>
              <span className="lbp-int-mono" aria-hidden="true">
                {i.slice(0, 1)}
              </span>
              <span>
                <strong>{i}</strong>
                <small>{g.group}</small>
              </span>
            </div>
          )),
        )}
      </div>
      <p className="lbp-small" style={{ marginTop: 18 }}>
        labbenchos reads details such as titles and modified dates. It never copies your data out of
        these services.
      </p>
    </div>
  );
}

export function FeaturesPage() {
  return (
    <>
      <PageHero
        theme="features"
        eyebrow="Features"
        title="Everything a lab needs, connected."
        lead="Every feature shares the same people, projects and records, so updating one place updates everywhere. Filter by what you care about."
        secondary={{ to: "#catalog", label: "Browse features" }}
      />

      <section id="catalog" className="lb-wrap lb-section">
        <SectionHead
          eyebrow="The full list"
          title="What's inside labbenchos."
          lead="Pick a category, then open any feature to see the details."
        />
        <Catalog />
      </section>

      <section id="integrations" className="lbp-band lbp-band-soft">
        <div className="lb-wrap lb-section">
          <SectionHead
            eyebrow="Integrations"
            title="Works with the tools your lab already uses."
            lead="Link files, code, references and repository records to your projects without moving anything."
          />
          <IntegrationWall />
        </div>
      </section>

      <section className="lb-wrap lb-section">
        <NextPages
          pages={[
            {
              to: "/workflow",
              title: "See the workflow",
              body: "How the features fit together, stage by stage.",
            },
            { to: "/for-labs", title: "For labs", body: "What PIs and lab managers get." },
            { to: "/for-students", title: "For students", body: "Getting started in a new lab." },
          ]}
        />
      </section>

      <CtaBand
        theme="features"
        title="See it with your own lab's work."
        body="We'll set up a lab for you and show you around."
      />
    </>
  );
}
