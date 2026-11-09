import { useState } from "react";
import { Link } from "react-router";
import logo from "@/assets/brand/labbenchos-logo.png";
import logoOnDark from "@/assets/brand/labbenchos-logo-dark-bg.png";
import { AI_MODELS, INTEGRATIONS, MODULES, PLANS, ROLES, STEPS } from "./content";
import "./landing.css";

const ACCENT = "#02851E";
const MINT = "#4ADE80";

function Icon({
  d,
  size = 24,
  color = ACCENT,
  width = 2,
}: {
  d: string;
  size?: number;
  color?: string;
  width?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={width}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}

const CHECK = "M5 12l5 5 9-10";
const SPARKLE =
  "M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z";

function Header() {
  return (
    <>
      <div className="lb-announce">
        New: bring your own AI to your lab&rsquo;s workspace.
        <a href="#d-ai">Learn more →</a>
      </div>
      <header className="lb-header">
        <nav className="lb-wrap lb-nav" aria-label="Main">
          <div className="lb-nav-left">
            <a href="#d-top">
              <img src={logo} alt="labbenchos" className="lb-logo" />
            </a>
            <div className="lb-nav-links">
              <a href="#d-platform">Features</a>
              <a href="#d-workflow">Workflow</a>
              <a href="#d-roles">For labs</a>
              <a href="#d-roles">For students</a>
              <a href="#d-roles">For institutions</a>
              <a href="#d-pricing">Pricing</a>
            </div>
          </div>
          <div className="lb-nav-right">
            <Link to="/login" className="lb-signin">
              Sign in
            </Link>
            <a href="#d-pricing" className="lb-btn lb-btn-sm lb-btn-dark">
              Contact us
            </a>
          </div>
        </nav>
      </header>
    </>
  );
}

function Hero() {
  return (
    <section id="d-top" className="lb-wrap lb-hero">
      <div className="lb-hero-copy">
        <p className="lb-pill">The lab operating system</p>
        <h1>Run your entire lab on one platform.</h1>
        <p className="lb-hero-sub">
          From ethics approval and funding to experiments and publication, labbenchos connects every
          step of your research with the tools and AI your lab already uses.
        </p>
        <div className="lb-actions">
          <a href="#d-pricing" className="lb-btn lb-btn-accent">
            Contact us
          </a>
          <a href="#d-workflow" className="lb-btn lb-btn-outline">
            See the workflow
          </a>
        </div>
      </div>

      <div className="lb-hero-art" aria-hidden="true">
        <div className="lb-mock">
          <div className="lb-mock-top">
            <span>[Project name] · Notebook</span>
            <span className="lb-tag">Ethics approved</span>
          </div>
          <div className="lb-mock-body">
            <div className="lb-mock-main">
              <p style={{ fontSize: 13, color: "#4A5260" }}>Entry · [Date]</p>
              <p style={{ fontSize: 18, fontWeight: 700 }}>
                [Experiment title, e.g. Pilot session 3]
              </p>
              <div className="lb-mock-line" style={{ width: "92%" }} />
              <div className="lb-mock-line" style={{ width: "78%" }} />
              <div className="lb-mock-line" style={{ width: "85%" }} />
              <div className="lb-mock-ai">
                <Icon d={SPARKLE} size={18} />
                <span>
                  <strong>AI assistant</strong>{" "}
                  <span style={{ color: "#4A5260" }}>(your lab&rsquo;s model)</span>: summarized 4
                  notebook entries and flagged 1 reagent running low.
                </span>
              </div>
            </div>
            <div className="lb-mock-side">
              <p className="lb-mock-label">Funding</p>
              <div className="lb-mock-row">
                <span>[Grant name]</span>
                <span className="lb-ok">Active</span>
              </div>
              <p className="lb-mock-label" style={{ marginTop: 6 }}>
                Materials
              </p>
              <div className="lb-mock-row">
                <span>[Reagent A]</span>
                <span className="lb-low">Low</span>
              </div>
              <div className="lb-mock-row">
                <span>[Reagent B]</span>
                <span className="lb-ok">OK</span>
              </div>
            </div>
          </div>
        </div>
        <div className="lb-float">
          <Icon
            d="M5 4h14a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM3 9h18M8 2v4M16 2v4"
            size={20}
          />
          <span>
            Synced with <strong>Google Calendar</strong>
          </span>
        </div>
      </div>
    </section>
  );
}

function Trust() {
  return (
    <section className="lb-trust" aria-label="Customers">
      <div className="lb-wrap lb-trust-inner">
        <p style={{ fontSize: 15, color: "#4A5260", fontWeight: 500 }}>
          Trusted by research groups at
        </p>
        <div className="lb-trust-logos">
          {[1, 2, 3, 4].map((n) => (
            <span key={n} className="lb-trust-logo">
              [Institution logo]
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function Platform() {
  return (
    <section id="d-platform" className="lb-wrap lb-section">
      <div className="lb-split">
        <div style={{ flex: "1 1 520px", minWidth: 0 }}>
          <p className="lb-eyebrow">Features</p>
          <h2 className="lb-h2" style={{ marginTop: 14, maxWidth: 680 }}>
            Everything your lab needs, connected.
          </h2>
        </div>
        <p className="lb-lead" style={{ flex: "1 1 360px", minWidth: 0, maxWidth: 440 }}>
          Every feature shares the same people, projects and records, so updating one place updates
          everywhere.
        </p>
      </div>
      <div className="lb-grid">
        {MODULES.map((m) => (
          <div key={m.title} className="lb-cell">
            <Icon d={m.icon} size={28} width={1.8} />
            <h3>{m.title}</h3>
            <p>{m.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Workflow() {
  const [index, setIndex] = useState(0);
  const step = STEPS[index]!;
  return (
    <section id="d-workflow" className="lb-dark">
      <div className="lb-wrap lb-section">
        <p className="lb-eyebrow">The research workflow</p>
        <h2 className="lb-h2" style={{ marginTop: 14, maxWidth: 760 }}>
          With you at every step, from first idea to final paper.
        </h2>
        <p style={{ marginTop: 16, fontSize: 18, color: "#C5CAD3", maxWidth: 620 }}>
          Click a step to see what labbenchos does for your lab at that stage.
        </p>

        <div role="tablist" aria-label="Workflow steps" className="lb-steps">
          {STEPS.map((s, i) => (
            <button
              key={s.label}
              type="button"
              role="tab"
              id={`lb-step-${i}`}
              aria-controls="lb-step-panel"
              aria-selected={i === index}
              data-done={i < index}
              className="lb-step"
              onClick={() => setIndex(i)}
            >
              <span className="lb-step-num">{i + 1}</span>
              <span className="lb-step-label">{s.label}</span>
            </button>
          ))}
        </div>

        <div
          id="lb-step-panel"
          role="tabpanel"
          aria-labelledby={`lb-step-${index}`}
          className="lb-step-panel"
        >
          <div>
            <p style={{ fontSize: 14, fontWeight: 700, color: MINT }}>
              Step {index + 1} of {STEPS.length}
            </p>
            <h3 className="lb-h3" style={{ marginTop: 10 }}>
              {step.title}
            </h3>
            <p style={{ marginTop: 14, fontSize: 18, lineHeight: 1.6, color: "#C5CAD3" }}>
              {step.body}
            </p>
            <div className="lb-actions" style={{ marginTop: 28 }}>
              <button
                type="button"
                className="lb-round lb-round-outline"
                onClick={() => setIndex(Math.max(index - 1, 0))}
              >
                ← Previous
              </button>
              <button
                type="button"
                className="lb-round lb-round-mint"
                onClick={() => setIndex(Math.min(index + 1, STEPS.length - 1))}
              >
                Next step →
              </button>
            </div>
          </div>
          <ul>
            {step.points.map((p) => (
              <li key={p.t} className="lb-step-point">
                <Icon d={CHECK} size={20} color={MINT} width={2.4} />
                <span>
                  <strong>{p.t}</strong>
                  <span className="lb-muted-dark">{p.d}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

function Integrations() {
  return (
    <section id="d-integrations" className="lb-wrap lb-section">
      <div className="lb-pair">
        <div className="lb-card lb-card-line">
          <p className="lb-eyebrow">Integrations</p>
          <h2 className="lb-h2-sm">Works with the tools you already use.</h2>
          <p className="lb-card-text">
            Connect Google Workspace and your other lab resources so files, calendars and references
            stay in sync, without copying anything by hand.
          </p>
          <div className="lb-chips">
            {INTEGRATIONS.map((i) => (
              <span key={i} className="lb-chip">
                {i}
              </span>
            ))}
          </div>
          <a
            href="#d-pricing"
            style={{ fontSize: 15, fontWeight: 700, textDecoration: "none", marginTop: 4 }}
          >
            Need another integration? Contact us →
          </a>
        </div>

        <div id="d-ai" className="lb-card lb-card-green">
          <p className="lb-eyebrow">Bring your own AI</p>
          <h2 className="lb-h2-sm">Use the AI your lab trusts.</h2>
          <p className="lb-card-text" style={{ color: "#3B424D" }}>
            Plug in Claude, ChatGPT, Gemini or your institution&rsquo;s approved model. Your AI
            works across your lab&rsquo;s notes, protocols and data, and only sees what each member
            has permission to see.
          </p>
          <div className="lb-models">
            {AI_MODELS.map((a) => (
              <div key={a.name} className="lb-model">
                <span>{a.name}</span>
                <span className="lb-tag">{a.tag}</span>
              </div>
            ))}
          </div>
          <ul className="lb-checks">
            <li>✓ Summarize notebooks and meeting notes</li>
            <li>✓ Draft ethics applications, grant sections and methods</li>
            <li>✓ Ask questions about your protocols and data</li>
          </ul>
        </div>
      </div>
    </section>
  );
}

function Roles() {
  const [roleId, setRoleId] = useState(ROLES[0]!.id);
  const role = ROLES.find((r) => r.id === roleId) ?? ROLES[0]!;
  return (
    <section id="d-roles" className="lb-grey">
      <div className="lb-wrap lb-section">
        <h2 className="lb-h2" style={{ textAlign: "center" }}>
          Built for every role in the lab
        </h2>
        <div role="tablist" aria-label="Roles" className="lb-tabs">
          {ROLES.map((r) => (
            <button
              key={r.id}
              type="button"
              role="tab"
              id={`lb-role-${r.id}`}
              aria-controls="lb-role-panel"
              aria-selected={r.id === role.id}
              className="lb-tab"
              onClick={() => setRoleId(r.id)}
            >
              {r.label}
            </button>
          ))}
        </div>
        <div
          id="lb-role-panel"
          role="tabpanel"
          aria-labelledby={`lb-role-${role.id}`}
          className="lb-role"
        >
          <div>
            <h3 className="lb-h3">{role.title}</h3>
            <p className="lb-lead" style={{ marginTop: 14 }}>
              {role.body}
            </p>
          </div>
          <ul>
            {role.points.map((p) => (
              <li key={p}>
                <span className="lb-tick">
                  <Icon d={CHECK} size={14} color="#036B19" width={3} />
                </span>
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

function Pricing() {
  return (
    <section id="d-pricing" className="lb-wrap lb-section">
      <div style={{ textAlign: "center" }}>
        <p className="lb-eyebrow">Pricing</p>
        <h2 className="lb-h2" style={{ marginTop: 14 }}>
          A plan for every scale of research.
        </h2>
        <p className="lb-lead" style={{ margin: "14px auto 0", maxWidth: 560 }}>
          Every plan is tailored to how you work. Contact us and we&rsquo;ll put together the right
          fit.
        </p>
      </div>
      <div className="lb-plans">
        {PLANS.map((pl) => (
          <div key={pl.name} className={pl.featured ? "lb-plan lb-plan-featured" : "lb-plan"}>
            {pl.featured && <span className="lb-popular">Most popular</span>}
            <h3>{pl.name}</h3>
            <p className="lb-plan-desc">{pl.desc}</p>
            <p className="lb-plan-price">Contact us</p>
            <a
              href="#d-pricing"
              className={`lb-btn lb-btn-block ${pl.featured ? "lb-btn-mint" : "lb-btn-dark"}`}
            >
              Contact sales
            </a>
            <ul>
              {pl.features.map((f) => (
                <li key={f}>
                  <Icon d={CHECK} size={18} color={pl.featured ? MINT : ACCENT} width={2.6} />
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

function Closing() {
  return (
    <section className="lb-wrap" style={{ paddingBottom: 112 }}>
      <figure className="lb-quote">
        <blockquote>
          &ldquo;[Customer quote from a real PI or lab manager goes here.]&rdquo;
        </blockquote>
        <figcaption>
          <strong>[Name]</strong> · [Role], [Lab / Institution]
        </figcaption>
      </figure>
      <div className="lb-cta">
        <h2 className="lb-h2">See your lab in labbenchos.</h2>
        <p>Tell us about your lab or institution and we&rsquo;ll walk you through it.</p>
        <div className="lb-actions">
          <a href="#d-pricing" className="lb-btn lb-btn-white">
            Contact us
          </a>
          <Link to="/login" className="lb-btn lb-btn-ghost-white">
            Sign in
          </Link>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="lb-footer">
      <div className="lb-wrap lb-footer-cols">
        <div className="lb-footer-col">
          <img
            src={logoOnDark}
            alt="labbenchos"
            style={{ height: 32, width: "auto", alignSelf: "flex-start" }}
          />
          <span>The lab operating system.</span>
        </div>
        <div className="lb-footer-col">
          <span className="lb-footer-head">Product</span>
          <a href="#d-platform">Features</a>
          <a href="#d-workflow">Workflow</a>
          <a href="#d-integrations">Integrations</a>
          <a href="#d-ai">Bring your own AI</a>
        </div>
        <div className="lb-footer-col">
          <span className="lb-footer-head">Plans</span>
          <a href="#d-pricing">Individual</a>
          <a href="#d-pricing">Lab</a>
          <a href="#d-pricing">Institution</a>
        </div>
        <div className="lb-footer-col">
          <span className="lb-footer-head">Company</span>
          <a href="#d-top">About</a>
          <a href="#d-pricing">Contact</a>
          <Link to="/login">Sign in</Link>
        </div>
      </div>
      <div className="lb-wrap lb-footer-bottom">
        <span>© {new Date().getFullYear()} labbenchos</span>
        <span>
          <a href="#d-top">Privacy</a> · <a href="#d-top">Terms</a>
        </span>
      </div>
    </footer>
  );
}

/** Public marketing home shown at "/" to signed-out visitors. Signing in leads into the app. */
export function MarketingHome() {
  return (
    <div className="lb">
      <Header />
      <main>
        <Hero />
        <Trust />
        <Platform />
        <Workflow />
        <Integrations />
        <Roles />
        <Pricing />
        <Closing />
      </main>
      <Footer />
    </div>
  );
}
