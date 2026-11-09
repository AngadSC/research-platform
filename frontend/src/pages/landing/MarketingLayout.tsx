import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import logo from "@/assets/brand/labbenchos-logo.png";
import logoOnDark from "@/assets/brand/labbenchos-logo-dark-bg.png";
import { CONTACT_PATH } from "./content";
import "./landing.css";
import "./subpages.css";

/** The public pages, in header order. Each one is its own route, not a section of the home page. */
const MARKETING_NAV = [
  { to: "/features", label: "Features" },
  { to: "/workflow", label: "Workflow" },
  { to: "/for-labs", label: "For labs" },
  { to: "/for-students", label: "For students" },
  { to: "/for-institutions", label: "For institutions" },
  { to: "/pricing", label: "Pricing" },
];

export function MarketingHeader() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <div className="lb-announce">
        New: bring your own AI to your lab&rsquo;s workspace.
        <Link to="/for-institutions#ai">Learn more →</Link>
      </div>
      <header className="lb-header">
        <nav className="lb-wrap lb-nav" aria-label="Main">
          <div className="lb-nav-left">
            <Link to="/" aria-label="labbenchos home">
              <img src={logo} alt="labbenchos" className="lb-logo" />
            </Link>
            <div className="lb-nav-links">
              {MARKETING_NAV.map((item) => (
                <NavLink key={item.to} to={item.to} className="lbp-navlink">
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
          <div className="lb-nav-right">
            <Link to="/login" className="lb-signin">
              Sign in
            </Link>
            <Link to={CONTACT_PATH} className="lb-btn lb-btn-sm lb-btn-dark lbp-hide-sm">
              Contact us
            </Link>
            <button
              type="button"
              className="lbp-menu-btn"
              aria-expanded={open}
              aria-controls="lbp-mobile-menu"
              onClick={() => setOpen((o) => !o)}
            >
              {open ? "Close" : "Menu"}
            </button>
          </div>
        </nav>
        {open && (
          <div id="lbp-mobile-menu" className="lbp-mobile-menu">
            {MARKETING_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className="lbp-navlink"
                onClick={() => setOpen(false)}
              >
                {item.label}
              </NavLink>
            ))}
            <Link
              to={CONTACT_PATH}
              className="lb-btn lb-btn-dark lb-btn-block"
              onClick={() => setOpen(false)}
            >
              Contact us
            </Link>
          </div>
        )}
      </header>
    </>
  );
}

export function MarketingFooter() {
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
          <Link to="/features">Features</Link>
          <Link to="/workflow">Workflow</Link>
          <Link to="/features#integrations">Integrations</Link>
          <Link to="/for-institutions#ai">Bring your own AI</Link>
        </div>
        <div className="lb-footer-col">
          <span className="lb-footer-head">Who it&rsquo;s for</span>
          <Link to="/for-labs">Labs and PIs</Link>
          <Link to="/for-students">Students and RAs</Link>
          <Link to="/for-institutions">Institutions</Link>
        </div>
        <div className="lb-footer-col">
          <span className="lb-footer-head">Company</span>
          <Link to="/pricing">Pricing</Link>
          <Link to={CONTACT_PATH}>Contact</Link>
          <Link to="/login">Sign in</Link>
        </div>
      </div>
      <div className="lb-wrap lb-footer-bottom">
        <span>© {new Date().getFullYear()} labbenchos</span>
        <span>
          <Link to="/">Privacy</Link> · <Link to="/">Terms</Link>
        </span>
      </div>
    </footer>
  );
}

/** Jumps to the top on a new page, or to the #section when the link names one. */
function ScrollManager() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      const el = document.getElementById(hash.slice(1));
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
    }
    window.scrollTo(0, 0);
  }, [pathname, hash]);
  return null;
}

export function MarketingShell({ children }: { children: ReactNode }) {
  return (
    <div className="lb">
      <ScrollManager />
      <MarketingHeader />
      <main>{children}</main>
      <MarketingFooter />
    </div>
  );
}

/** Route element for every public page except the home page, which renders its own shell. */
export function MarketingLayout() {
  return (
    <MarketingShell>
      <Outlet />
    </MarketingShell>
  );
}
