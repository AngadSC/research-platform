import { useId, useState, type CSSProperties, type ReactNode } from "react";
import { Link } from "react-router";
import { CONTACT_PATH } from "./content";
import { ICONS } from "./icons";

export { ICONS };

export function Icon({
  d,
  size = 24,
  color = "currentColor",
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

export function Check({ ok = true, size = 16 }: { ok?: boolean; size?: number }) {
  return (
    <span className={ok ? "lbp-yes" : "lbp-no"}>
      <Icon d={ok ? ICONS.check : ICONS.cross} size={size} width={3} />
      <span className="lbp-sr">{ok ? "Yes" : "No"}</span>
    </span>
  );
}

/** Top of every subpage: coloured background, headline, two buttons and an optional picture. */
export function PageHero({
  theme,
  eyebrow,
  title,
  lead,
  primary,
  secondary,
  art,
}: {
  theme: "labs" | "students" | "institutions" | "features" | "workflow" | "pricing";
  eyebrow: string;
  title: string;
  lead: string;
  primary?: { to: string; label: string };
  secondary?: { to: string; label: string };
  art?: ReactNode;
}) {
  return (
    <section className={`lbp-hero lbp-theme-${theme}`}>
      <div className="lbp-blob lbp-blob-1" aria-hidden="true" />
      <div className="lbp-blob lbp-blob-2" aria-hidden="true" />
      <div className="lb-wrap lbp-hero-inner">
        <div className="lbp-hero-copy">
          <p className="lbp-eyebrow-pill">{eyebrow}</p>
          <h1>{title}</h1>
          <p className="lbp-hero-lead">{lead}</p>
          <div className="lb-actions">
            <Link to={primary?.to ?? CONTACT_PATH} className="lbp-btn lbp-btn-primary">
              {primary?.label ?? "Contact us"}
            </Link>
            {secondary && (
              <Link to={secondary.to} className="lbp-btn lbp-btn-ghost">
                {secondary.label}
              </Link>
            )}
          </div>
        </div>
        {art && <div className="lbp-hero-art">{art}</div>}
      </div>
    </section>
  );
}

export function SectionHead({
  eyebrow,
  title,
  lead,
  center = false,
}: {
  eyebrow?: string;
  title: string;
  lead?: string;
  center?: boolean;
}) {
  return (
    <div className={center ? "lbp-head lbp-head-center" : "lbp-head"}>
      {eyebrow && <p className="lbp-eyebrow">{eyebrow}</p>}
      <h2 className="lb-h2">{title}</h2>
      {lead && <p className="lb-lead">{lead}</p>}
    </div>
  );
}

/** Small coloured tile used for feature grids. `tone` picks one of the palette colours. */
export function Tile({
  icon,
  title,
  body,
  tone = "green",
  children,
}: {
  icon: string;
  title: string;
  body: string;
  tone?: Tone;
  children?: ReactNode;
}) {
  return (
    <div className={`lbp-tile lbp-tone-${tone}`}>
      <span className="lbp-tile-icon">
        <Icon d={icon} size={22} />
      </span>
      <h3>{title}</h3>
      <p>{body}</p>
      {children}
    </div>
  );
}

export type Tone = "green" | "blue" | "violet" | "pink" | "amber" | "teal" | "red";

export function Faq({ items }: { items: { q: string; a: string }[] }) {
  const [open, setOpen] = useState<number | null>(0);
  const base = useId();
  return (
    <div className="lbp-faq">
      {items.map((item, i) => {
        const isOpen = open === i;
        return (
          <div key={item.q} className="lbp-faq-item" data-open={isOpen}>
            <h3>
              <button
                type="button"
                aria-expanded={isOpen}
                aria-controls={`${base}-${i}`}
                onClick={() => setOpen(isOpen ? null : i)}
              >
                <span>{item.q}</span>
                <span className="lbp-faq-sign" aria-hidden="true">
                  {isOpen ? "−" : "+"}
                </span>
              </button>
            </h3>
            <div id={`${base}-${i}`} hidden={!isOpen} className="lbp-faq-answer">
              <p>{item.a}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function CtaBand({
  title,
  body,
  theme = "labs",
}: {
  title: string;
  body: string;
  theme?: string;
}) {
  return (
    <section className="lb-wrap" style={{ paddingBottom: 112 }}>
      <div className={`lbp-cta lbp-theme-${theme}`}>
        <h2 className="lb-h2">{title}</h2>
        <p>{body}</p>
        <div className="lb-actions">
          <Link to={CONTACT_PATH} className="lb-btn lb-btn-white">
            Contact us
          </Link>
          <Link to="/signup" className="lb-btn lb-btn-ghost-white">
            Create an account
          </Link>
        </div>
      </div>
    </section>
  );
}

/** Row of "see also" cards at the bottom of a page, so each page leads to the next. */
export function NextPages({ pages }: { pages: { to: string; title: string; body: string }[] }) {
  return (
    <div className="lbp-next">
      {pages.map((p) => (
        <Link key={p.to} to={p.to} className="lbp-next-card">
          <strong>{p.title}</strong>
          <span>{p.body}</span>
          <span className="lbp-next-go">
            Go <Icon d={ICONS.arrow} size={16} />
          </span>
        </Link>
      ))}
    </div>
  );
}

export function Pill({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <span className="lbp-pill" style={style}>
      {children}
    </span>
  );
}
