import { useState } from "react";
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

const PILLARS: { icon: string; title: string; body: string; tone: Tone; more: string[] }[] = [
  {
    icon: ICONS.lock,
    title: "Every lab walled off",
    body: "Each lab's records are kept apart at the database level, and every request is checked against the lab it belongs to.",
    tone: "blue",
    more: [
      "Lab-scoped records enforced by database constraints, not just app code",
      "Automated tests try every endpoint as every role, plus a user from another lab",
      "A new endpoint can't ship until it's added to that test",
    ],
  },
  {
    icon: ICONS.eye,
    title: "A full audit trail",
    body: "An append-only log of who viewed, downloaded, exported, changed roles or deleted what, when and from where.",
    tone: "violet",
    more: [
      "Document views, downloads and exports",
      "Membership and permission changes",
      "Filter by person, action and date",
    ],
  },
  {
    icon: ICONS.shield,
    title: "No raw participant data",
    body: "labbenchos stores notes, documents, anonymized results and pointers to where datasets live. Identifiable data stays in your approved systems.",
    tone: "green",
    more: [
      "Upload notice on every file, with acknowledgement logged",
      "Recruitment is tracked as counts only",
      "REDCap and Qualtrics links read titles and settings, never records",
    ],
  },
  {
    icon: ICONS.key,
    title: "Strong sign-in",
    body: "University single sign-on through SAML, Google sign-in, and two-step verification with any authenticator app.",
    tone: "amber",
    more: [
      "Option to require SSO for everyone at your institution",
      "Re-authentication before sensitive changes",
      "Accounts linked to institutional domains only after verification",
    ],
  },
  {
    icon: ICONS.link,
    title: "Careful with other systems",
    body: "Connections to Drive, GitHub, Zotero and others read only the details needed, like titles and modified dates.",
    tone: "teal",
    more: [
      "Tokens encrypted at rest, with key rotation",
      "Connections revoked when a member is removed",
      "Files served only through permission-checked downloads",
    ],
  },
  {
    icon: ICONS.archive,
    title: "Retention you control",
    body: "Set keep-until dates on projects and documents. Items past their date are listed for review. Nothing is deleted automatically.",
    tone: "pink",
    more: [
      "Daily retention check",
      "Project export with a notice sent to the PI",
      "Handover reports so records outlive staff turnover",
    ],
  },
];

const POLICIES = [
  {
    id: "both",
    label: "MCP and in-app assistant",
    body: "Members may connect their own AI app, and use the assistant built into labbenchos with their own key.",
    allow: [true, true, true],
  },
  {
    id: "mcp",
    label: "MCP only",
    body: "Members may connect their own AI app, like Claude or ChatGPT. The built-in assistant is turned off.",
    allow: [true, false, true],
  },
  {
    id: "off",
    label: "Off",
    body: "No AI assistant of any kind can read this lab. Connected apps get an error.",
    allow: [false, false, false],
  },
];
const AI_ABILITIES = [
  "Connect Claude, ChatGPT or another MCP app",
  "Use the built-in assistant with their own key",
  "Let AI draft tasks and decisions (approved before saving)",
];

const CANADA: { icon: string; title: string; body: string; tone: Tone }[] = [
  {
    icon: ICONS.doc,
    title: "Tri-Agency data management plans",
    body: "Write a DMP for each project, following the Tri-Agency RDM Policy and the Portage DMP Assistant template, with lead approval and history.",
    tone: "blue",
  },
  {
    icon: ICONS.building,
    title: "Your institution's resources, built in",
    body: "Choose your university and its ethics office, ethics application system, internal funding and RDM pages appear in every project's workflow.",
    tone: "violet",
  },
  {
    icon: ICONS.archive,
    title: "Canadian repositories",
    body: "Link deposits in Borealis and the Federated Research Data Repository (FRDR), alongside Zenodo, Figshare and OSF.",
    tone: "teal",
  },
  {
    icon: ICONS.shield,
    title: "Ethics tracking that fits REB practice",
    body: "Approval numbers, boards, linked projects, expiry dates and attached documents, with renewal reminders to the right people.",
    tone: "green",
  },
];

const ROLLOUT = [
  {
    step: "Pilot",
    title: "A few labs, a few weeks",
    body: "Start with two or three interested labs. We set them up, load your institution's resources and gather feedback.",
  },
  {
    step: "Review",
    title: "Security and privacy review",
    body: "We work through your IT security and privacy questionnaires, and set up SAML single sign-on with your identity team.",
  },
  {
    step: "Department",
    title: "Open it to a department",
    body: "Labs in the department join with SSO. Required trainings and onboarding checklists are set per lab.",
  },
  {
    step: "Institution",
    title: "Every lab that wants it",
    body: "An institutional agreement covers all labs, with dedicated onboarding and support.",
  },
];

const FAQS = [
  {
    q: "Where is our data stored?",
    a: "Tell us your requirements and we'll go through hosting and data location with your IT and privacy teams as part of the review.",
  },
  {
    q: "Can we require everyone to sign in with university SSO?",
    a: "Yes. Once SAML is set up for your institution, you can require SSO for every account with an address at your domain, whichever way they try to sign in.",
  },
  {
    q: "What does the AI see?",
    a: "Only what the member using it can already see, in the labs they chose when connecting. Content goes to the member's own AI provider under their own account. Labs can turn AI off entirely.",
  },
  {
    q: "Does labbenchos replace our electronic lab notebook?",
    a: "Not necessarily. labbenchos covers what happens around the research: ethics, funding, data plans, training, handovers and the record of how results were made. Many labs use it alongside their existing tools.",
  },
  {
    q: "Can other universities' resources be added?",
    a: "Yes. Institution resources are links with a category and description. We load a starter set for your institution and lab admins can add their own.",
  },
];

function PillarCard({ p }: { p: (typeof PILLARS)[number] }) {
  const [open, setOpen] = useState(false);
  return (
    <Tile icon={p.icon} title={p.title} body={p.body} tone={p.tone}>
      <button
        type="button"
        className="lbp-link-btn"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? "Show less" : "How it works"}
      </button>
      {open && (
        <ul className="lbp-more">
          {p.more.map((m) => (
            <li key={m}>
              <Check size={14} />
              {m}
            </li>
          ))}
        </ul>
      )}
    </Tile>
  );
}

function AiPolicy() {
  const [id, setId] = useState("both");
  const pol = POLICIES.find((p) => p.id === id)!;
  return (
    <div className="lbp-perm">
      <div role="radiogroup" aria-label="AI policy for a lab" className="lbp-seg">
        {POLICIES.map((p) => (
          <button
            key={p.id}
            type="button"
            role="radio"
            aria-checked={p.id === id}
            onClick={() => setId(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="lbp-perm-panel" aria-live="polite">
        <p className="lbp-body">{pol.body}</p>
        <ul className="lbp-perm-list">
          {AI_ABILITIES.map((a, n) => (
            <li key={a} data-ok={pol.allow[n]}>
              <Check ok={pol.allow[n]} />
              {a}
            </li>
          ))}
        </ul>
        <p className="lbp-small">
          Set per lab by the PI. Whatever the setting, AI only reaches what the member can see, and
          every connection is listed so it can be removed at once.
        </p>
      </div>
    </div>
  );
}

export function InstitutionsPage() {
  return (
    <>
      <PageHero
        theme="institutions"
        eyebrow="For research offices, departments and IT"
        title="Better research data management, without a new burden for labs."
        lead="Give every lab one place for ethics, data plans, training and the record of how results were made, with the security and oversight your institution needs."
        secondary={{ to: "#security", label: "Security and privacy" }}
        art={
          <div className="lbp-art-card">
            <p className="lbp-art-title">Institution sign-in</p>
            <div className="lbp-art-field">name@ualberta.ca</div>
            <div className="lbp-art-sso">
              <Icon d={ICONS.building} size={18} /> Continue with University SSO
            </div>
            <div className="lbp-art-badge">
              <Icon d={ICONS.shield} size={18} /> SSO required for this domain
            </div>
          </div>
        }
      />

      <section id="security" className="lb-wrap lb-section">
        <SectionHead
          eyebrow="Security and privacy"
          title="Built for research with people."
          lead="Designed from the start for human-participant research. Open any card to see how it works."
        />
        <div className="lbp-tiles">
          {PILLARS.map((p) => (
            <PillarCard key={p.title} p={p} />
          ))}
        </div>
      </section>

      <section id="ai" className="lbp-band lbp-band-institutions">
        <div className="lb-wrap lb-section">
          <div className="lbp-two">
            <div>
              <SectionHead
                eyebrow="AI, on your terms"
                title="Bring your own AI, with a lab-level off switch."
                lead="Researchers can use the AI their institution approves, under their own accounts. Nothing is sent to an AI provider unless a member chooses to, and labs with sensitive data can turn it off."
              />
              <ul className="lbp-ticks">
                <li>
                  <Check /> Connects through MCP, the open standard Claude and ChatGPT support
                </li>
                <li>
                  <Check /> Read-only access to one lab by default when connecting
                </li>
                <li>
                  <Check /> Every write is shown to the member for approval first
                </li>
                <li>
                  <Check /> All AI access revoked when a password or two-step setting changes
                </li>
              </ul>
            </div>
            <AiPolicy />
          </div>
        </div>
      </section>

      <section className="lb-wrap lb-section">
        <SectionHead
          eyebrow="Made for Canadian research"
          title="Aligned with how Canadian labs already work."
          lead="Built with the Tri-Agency requirements and Canadian research infrastructure in mind."
        />
        <div className="lbp-tiles lbp-tiles-2">
          {CANADA.map((c) => (
            <Tile key={c.title} {...c} />
          ))}
        </div>
      </section>

      <section className="lbp-band lbp-band-dark">
        <div className="lb-wrap lb-section">
          <SectionHead
            eyebrow="Rolling it out"
            title="Start small, then grow."
            lead="A typical path from first pilot to institution-wide use."
          />
          <ol className="lbp-timeline">
            {ROLLOUT.map((r, n) => (
              <li key={r.step}>
                <span className="lbp-timeline-num">{n + 1}</span>
                <p className="lbp-kicker">{r.step}</p>
                <h3>{r.title}</h3>
                <p>{r.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="lbp-band lbp-band-soft">
        <div className="lb-wrap lb-section">
          <SectionHead eyebrow="Questions" title="What research offices ask us." center />
          <Faq items={FAQS} />
        </div>
      </section>

      <section className="lb-wrap lb-section">
        <NextPages
          pages={[
            { to: "/for-labs", title: "For labs", body: "What PIs and lab managers get." },
            { to: "/features", title: "All features", body: "Every part of the platform." },
            { to: "/pricing", title: "Pricing", body: "The Institution plan, and the others." },
          ]}
        />
      </section>

      <CtaBand
        theme="institutions"
        title="Talk to us about a pilot."
        body="We'll help you pick a few labs, answer your security questions and get them running."
      />
    </>
  );
}
