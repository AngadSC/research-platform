import { useState } from "react";
import {
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

const PERKS: { icon: string; title: string; body: string; tone: Tone }[] = [
  {
    icon: ICONS.tasks,
    title: "Know what to do next",
    body: "Your tasks across every project, with due dates, attached documents and a comment thread on each one.",
    tone: "violet",
  },
  {
    icon: ICONS.cap,
    title: "Training without the paperwork",
    body: "See which trainings your lab requires, log a completion, attach your certificate and get reminded before it expires.",
    tone: "pink",
  },
  {
    icon: ICONS.doc,
    title: "Notes that never get lost",
    body: "Write protocols and notes in a clean editor. Every save is kept, so you can look back or restore an older version.",
    tone: "blue",
  },
  {
    icon: ICONS.book,
    title: "Your lab's reading list",
    body: "A shared paper library. Paste a DOI to fill in the details, attach the PDF and read it right in the browser.",
    tone: "amber",
  },
  {
    icon: ICONS.chat,
    title: "Ask in the right place",
    body: "A chat room for the whole lab and one for each project, so questions stay next to the work they're about.",
    tone: "teal",
  },
  {
    icon: ICONS.search,
    title: "Find anything fast",
    body: "Press Ctrl or Cmd + K to search projects, tasks, documents, datasets and ethics approvals from anywhere.",
    tone: "green",
  },
];

const WEEK = [
  {
    day: "Day 1",
    title: "Join your lab",
    body: "Your PI or lab admin sends an invitation to your university email. Accept it, sign in with your email or Google, and you land straight in your lab.",
    where: "Invitation email → Sign in",
    tip: "Turn on two-step verification in Settings → Security. It takes a minute with any authenticator app.",
  },
  {
    day: "Day 2",
    title: "Clear your required training",
    body: "My training lists what your lab expects of you, like research ethics or data privacy courses. Log each completion and attach the certificate.",
    where: "Sidebar → My training",
    tip: "Expiry dates are worked out for you, and you get a reminder 60, 30 and 7 days before one lapses.",
  },
  {
    day: "Day 3",
    title: "Get to know the project",
    body: "Open your project's Overview for its description, deadlines and who's involved. The Workflow tab shows where the study is, from ethics to manuscript.",
    where: "Projects → your project → Overview",
    tip: "Read the linked ethics approval before you touch any study materials.",
  },
  {
    day: "Day 4",
    title: "Pick up your first task",
    body: "Open a task to see what's needed, the documents attached to it and any discussion. Move it to In progress, then Done when you're finished.",
    where: "Project → Tasks (board or list)",
    tip: "Post questions in the task's thread. Your lead is notified and the answer stays with the task.",
  },
  {
    day: "Day 5",
    title: "Write it down",
    body: "Start a document for your session notes or protocol. Upload anonymized files, and record the datasets and analyses you work with.",
    where: "Project → Documents / Files / Workflow",
    tip: "Never upload names or other identifiers. Raw participant data stays in REDCap or your approved system.",
  },
];

type Status = "todo" | "doing" | "done";
const COLUMNS: { id: Status; label: string }[] = [
  { id: "todo", label: "To do" },
  { id: "doing", label: "In progress" },
  { id: "done", label: "Done" },
];
const START_TASKS: { id: number; title: string; due: string; status: Status }[] = [
  { id: 1, title: "Complete TCPS 2 CORE training", due: "Fri", status: "todo" },
  { id: 2, title: "Read the study protocol", due: "Wed", status: "todo" },
  { id: 3, title: "Pilot session notes", due: "Thu", status: "doing" },
  { id: 4, title: "Set up two-step verification", due: "Today", status: "done" },
];
const NEXT: Record<Status, Status> = { todo: "doing", doing: "done", done: "todo" };

const PROMPTS = [
  {
    q: "What's due for me this week?",
    a: "You have 3 open tasks. “Read the study protocol” is due Wednesday, “Pilot session notes” Thursday and “Complete TCPS 2 CORE training” Friday.",
  },
  {
    q: "Summarize last week's pilot notes",
    a: "Two pilot sessions ran. Both finished on time; one participant found the second task confusing, and the team agreed to reword its instructions before the next session.",
  },
  {
    q: "Which dataset did the March analysis use?",
    a: "“Main analysis, March” used Survey export v2. The code is in the lab's GitHub repository at the commit recorded on the analysis.",
  },
];

const FAQS = [
  {
    q: "Do I have to pay for labbenchos?",
    a: "No. When your lab uses labbenchos, its plan covers everyone your PI invites. You just accept the invitation.",
  },
  {
    q: "Who can see my training records?",
    a: "Only you, your PI and your lab admins. Other lab members can't see them.",
  },
  {
    q: "What happens to my work when I graduate?",
    a: "It stays with the lab. Your PI can create a handover report listing your open tasks, documents, datasets and analyses, and pass each one to someone else. Nothing gets lost in your personal Drive.",
  },
  {
    q: "Can I use Claude or ChatGPT with it?",
    a: "Yes, if your lab allows it. You can connect your own AI app or add your own API key for the built-in assistant. The AI only sees what you can already see.",
  },
  {
    q: "Can I store participant data here?",
    a: "No. labbenchos holds notes, documents, anonymized results and links to where data lives. Raw or identifying participant data stays in your institution's approved system, such as REDCap.",
  },
];

function TaskBoardDemo() {
  const [tasks, setTasks] = useState(START_TASKS);
  const done = tasks.filter((t) => t.status === "done").length;
  const pct = Math.round((done / tasks.length) * 100);
  return (
    <div className="lbp-demo">
      <div className="lbp-demo-bar">
        <div>
          <strong>Your board</strong>
          <span>Click a card to move it along.</span>
        </div>
        <button type="button" className="lbp-link-btn" onClick={() => setTasks(START_TASKS)}>
          Reset
        </button>
      </div>
      <div
        className="lbp-progress"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Tasks done"
      >
        <span style={{ width: `${pct}%` }} />
      </div>
      <p className="lbp-progress-label" aria-live="polite">
        {done === tasks.length
          ? "Everything's done. Nice week! 🎉"
          : `${done} of ${tasks.length} tasks done`}
      </p>
      <div className="lbp-board">
        {COLUMNS.map((col) => (
          <div key={col.id} className={`lbp-col lbp-col-${col.id}`}>
            <p className="lbp-col-head">
              {col.label}
              <span>{tasks.filter((t) => t.status === col.id).length}</span>
            </p>
            {tasks
              .filter((t) => t.status === col.id)
              .map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className="lbp-card-task"
                  onClick={() =>
                    setTasks((all) =>
                      all.map((x) => (x.id === t.id ? { ...x, status: NEXT[x.status] } : x)),
                    )
                  }
                  aria-label={`${t.title}, ${col.label}. Move to ${
                    COLUMNS.find((c) => c.id === NEXT[t.status])!.label
                  }`}
                >
                  <span>{t.title}</span>
                  <small>Due {t.due}</small>
                </button>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function FirstWeek() {
  const [i, setI] = useState(0);
  const d = WEEK[i]!;
  return (
    <div className="lbp-week">
      <div role="tablist" aria-label="Your first week" className="lbp-week-tabs">
        {WEEK.map((w, n) => (
          <button
            key={w.day}
            type="button"
            role="tab"
            id={`lbp-day-${n}`}
            aria-controls="lbp-day-panel"
            aria-selected={n === i}
            data-done={n < i}
            onClick={() => setI(n)}
          >
            <span className="lbp-week-dot">{n < i ? "✓" : n + 1}</span>
            {w.day}
          </button>
        ))}
      </div>
      <div
        id="lbp-day-panel"
        role="tabpanel"
        aria-labelledby={`lbp-day-${i}`}
        className="lbp-week-panel"
      >
        <div>
          <p className="lbp-kicker">{d.day}</p>
          <h3 className="lb-h3">{d.title}</h3>
          <p className="lbp-body">{d.body}</p>
          <p className="lbp-where">
            <Icon d={ICONS.arrow} size={16} /> {d.where}
          </p>
        </div>
        <div className="lbp-tip">
          <strong>Tip</strong>
          <p>{d.tip}</p>
          <div className="lb-actions" style={{ marginTop: 18 }}>
            <button
              type="button"
              className="lbp-btn lbp-btn-soft"
              disabled={i === 0}
              onClick={() => setI(i - 1)}
            >
              ← Back
            </button>
            <button
              type="button"
              className="lbp-btn lbp-btn-primary"
              disabled={i === WEEK.length - 1}
              onClick={() => setI(i + 1)}
            >
              Next day →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function AssistantDemo() {
  const [pick, setPick] = useState(0);
  const p = PROMPTS[pick]!;
  return (
    <div className="lbp-ai">
      <div className="lbp-ai-prompts" role="group" aria-label="Example questions">
        {PROMPTS.map((x, n) => (
          <button
            key={x.q}
            type="button"
            aria-pressed={n === pick}
            className="lbp-chip-btn"
            onClick={() => setPick(n)}
          >
            {x.q}
          </button>
        ))}
      </div>
      <div className="lbp-ai-window" aria-live="polite">
        <p className="lbp-ai-q">{p.q}</p>
        <p className="lbp-ai-a">
          <Icon d={ICONS.sparkle} size={18} />
          <span key={pick} className="lbp-type">
            {p.a}
          </span>
        </p>
        <p className="lbp-ai-note">
          Example answer. Real answers come from your lab&rsquo;s records, through the AI provider
          you connect.
        </p>
      </div>
    </div>
  );
}

function HeroArt() {
  return (
    <div className="lbp-art-card">
      <p className="lbp-art-title">My week</p>
      {[
        ["Complete TCPS 2 CORE", "Training", "pink"],
        ["Pilot session notes", "Task · Thu", "violet"],
        ["Read the protocol", "Task · Wed", "blue"],
      ].map(([t, s, c]) => (
        <div key={t} className={`lbp-art-row lbp-tone-${c}`}>
          <span className="lbp-art-dot" />
          <span>
            <strong>{t}</strong>
            <small>{s}</small>
          </span>
        </div>
      ))}
      <div className="lbp-art-badge">
        <Icon d={ICONS.cap} size={18} /> 2 of 3 trainings done
      </div>
    </div>
  );
}

export function StudentsPage() {
  return (
    <>
      <PageHero
        theme="students"
        eyebrow="For students and research assistants"
        title="Your first research lab, without the confusion."
        lead="Know what's expected of you from day one. Your tasks, training, notes and the lab's knowledge, all in one place that's easy to find your way around."
        primary={{ to: "/signup", label: "Create an account" }}
        secondary={{ to: "#first-week", label: "See your first week" }}
        art={<HeroArt />}
      />

      <section className="lb-wrap lb-section">
        <SectionHead
          eyebrow="What you get"
          title="Everything you need to be useful in your lab fast."
          lead="No digging through shared drives or old email threads to work out what to do."
        />
        <div className="lbp-tiles">
          {PERKS.map((p) => (
            <Tile key={p.title} {...p} />
          ))}
        </div>
      </section>

      <section id="first-week" className="lbp-band lbp-band-students">
        <div className="lb-wrap lb-section">
          <SectionHead
            eyebrow="Your first week"
            title="From invitation to your first finished task."
            lead="Click through the days to see where everything is."
          />
          <FirstWeek />
        </div>
      </section>

      <section className="lb-wrap lb-section">
        <div className="lbp-two">
          <div>
            <SectionHead
              eyebrow="Tasks"
              title="See your progress, not just your to-do list."
              lead="Every project has a board and a list. Open a task to find its documents, files and discussion in one place. Try it here."
            />
          </div>
          <TaskBoardDemo />
        </div>
      </section>

      <section className="lbp-band lbp-band-dark">
        <div className="lb-wrap lb-section">
          <div className="lbp-two">
            <div>
              <SectionHead
                eyebrow="Bring your own AI"
                title="Ask questions about your lab's work."
                lead="Connect Claude, ChatGPT or another AI app, or add your own API key to the built-in assistant. It only sees what you can see, and it asks before changing anything."
              />
            </div>
            <AssistantDemo />
          </div>
        </div>
      </section>

      <section className="lb-wrap lb-section">
        <SectionHead
          eyebrow="Keep participants safe"
          title="Clear rules about what goes where."
          center
        />
        <div className="lbp-dodont">
          <div className="lbp-do">
            <h3>
              <Icon d={ICONS.check} size={20} /> Put in labbenchos
            </h3>
            <ul>
              <li>Notes, protocols and write-ups</li>
              <li>Anonymized or aggregate data files</li>
              <li>Links to where datasets live</li>
              <li>Recruitment counts (screened, enrolled, withdrawn)</li>
            </ul>
          </div>
          <div className="lbp-dont">
            <h3>
              <Icon d={ICONS.cross} size={20} /> Keep in your approved system
            </h3>
            <ul>
              <li>Participant names and contact details</li>
              <li>Raw identifiable data</li>
              <li>Consent forms with signatures</li>
              <li>Anything your ethics approval says stays elsewhere</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="lbp-band lbp-band-soft">
        <div className="lb-wrap lb-section">
          <SectionHead eyebrow="Questions" title="Things students ask us." center />
          <Faq items={FAQS} />
        </div>
      </section>

      <section className="lb-wrap lb-section">
        <NextPages
          pages={[
            {
              to: "/for-labs",
              title: "Show your PI",
              body: "What labbenchos does for PIs and lab managers.",
            },
            {
              to: "/workflow",
              title: "The research workflow",
              body: "Every stage from funding to manuscript.",
            },
            { to: "/features", title: "All features", body: "Browse everything in one place." },
          ]}
        />
      </section>

      <CtaBand
        theme="students"
        title="Want your lab on labbenchos?"
        body="Send this page to your PI, or get in touch and we'll walk your lab through it."
      />
    </>
  );
}
