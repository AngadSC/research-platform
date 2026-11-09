import { useState } from "react";
import { Link } from "react-router";
import { CONTACT_EMAIL, PLANS } from "../content";
import { Faq, Icon, ICONS, PageHero, SectionHead } from "../shared";

const WHO = [
  { id: "me", label: "Just me", plan: "Individual" },
  { id: "lab", label: "My lab or research group", plan: "Lab" },
  { id: "many", label: "A department or institution", plan: "Institution" },
];

const FAQS = [
  {
    q: "Why is there no price on the page?",
    a: "We're working with our first labs and institutions now, and set each plan up around how you work. Get in touch and we'll put together a quote.",
  },
  {
    q: "Do students pay?",
    a: "No. Everyone a PI invites is covered by the lab's plan.",
  },
  {
    q: "Does the AI cost extra?",
    a: "No. You use your own AI account or API key, so any AI usage is billed by your provider, not by us.",
  },
  {
    q: "Can we start with a pilot?",
    a: "Yes. Most labs and institutions start with a short pilot before committing.",
  },
];

export function PricingPage() {
  const [who, setWho] = useState<string | null>(null);
  const match = WHO.find((w) => w.id === who)?.plan;

  return (
    <>
      <PageHero
        theme="pricing"
        eyebrow="Pricing"
        title="A plan for every scale of research."
        lead="From one researcher to a whole institution. Tell us how you work and we'll put together the right plan."
        primary={{ to: "#contact", label: "Contact us" }}
        secondary={{ to: "#plans", label: "See the plans" }}
      />

      <section id="plans" className="lb-wrap lb-section">
        <div className="lbp-finder">
          <p className="lbp-kicker">Which plan fits?</p>
          <h2 className="lb-h2-sm">Who will use labbenchos?</h2>
          <div className="lbp-seg" role="radiogroup" aria-label="Who will use labbenchos">
            {WHO.map((w) => (
              <button
                key={w.id}
                type="button"
                role="radio"
                aria-checked={w.id === who}
                onClick={() => setWho(w.id)}
              >
                {w.label}
              </button>
            ))}
          </div>
          <p className="lbp-finder-answer" aria-live="polite">
            {match ? (
              <>
                We&rsquo;d suggest the <strong>{match}</strong> plan. It&rsquo;s highlighted below.
              </>
            ) : (
              "Pick one and we'll highlight the plan that fits."
            )}
          </p>
        </div>

        <div className="lb-plans">
          {PLANS.map((pl) => {
            const picked = match === pl.name;
            return (
              <div
                key={pl.name}
                className={`lb-plan ${pl.featured ? "lb-plan-featured" : ""} lbp-plan`}
                data-picked={picked}
              >
                {picked ? (
                  <span className="lb-popular lbp-match">Best fit for you</span>
                ) : (
                  pl.featured && <span className="lb-popular">Most popular</span>
                )}
                <h3>{pl.name}</h3>
                <p className="lb-plan-desc">{pl.desc}</p>
                <p className="lb-plan-price">Contact us</p>
                <Link
                  to="#contact"
                  className={`lb-btn lb-btn-block ${pl.featured ? "lb-btn-mint" : "lb-btn-dark"}`}
                >
                  Get a quote
                </Link>
                <ul>
                  {pl.features.map((f) => (
                    <li key={f}>
                      <Icon
                        d={ICONS.check}
                        size={18}
                        color={pl.featured ? "#4ADE80" : "#02851E"}
                        width={2.6}
                      />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </section>

      <section id="contact" className="lb-wrap lb-section">
        <div className="lbp-contact">
          <div>
            <p className="lbp-kicker">Contact us</p>
            <h2 className="lb-h2">Tell us about your lab.</h2>
            <p className="lb-lead" style={{ marginTop: 14 }}>
              Let us know who you are, how many people are in your lab or department, and what
              you&rsquo;d most like to fix. We&rsquo;ll get back to you with a plan and a time to
              walk you through it.
            </p>
          </div>
          <div className="lbp-contact-card">
            {CONTACT_EMAIL ? (
              <a
                className="lbp-btn lbp-btn-primary"
                href={`mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("labbenchos enquiry")}`}
              >
                Email {CONTACT_EMAIL}
              </a>
            ) : (
              <span className="lbp-btn lbp-btn-primary" aria-disabled="true">
                [Contact email]
              </span>
            )}
            <Link to="/signup" className="lbp-btn lbp-btn-soft">
              Or create an account and look around
            </Link>
          </div>
        </div>
      </section>

      <section className="lbp-band lbp-band-soft">
        <div className="lb-wrap lb-section">
          <SectionHead eyebrow="Questions" title="About plans and pricing." center />
          <Faq items={FAQS} />
        </div>
      </section>
    </>
  );
}
