import { FileCheck2, GitBranch, Plug, UserRoundCheck } from "lucide-react";
import { Link } from "react-router";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { Button } from "@/components/ui/button";
import logo from "@/assets/brand/labbenchos-logo.png";
import logoOnDark from "@/assets/brand/labbenchos-logo-dark-bg.png";
import { MarketingHome } from "@/pages/landing/MarketingHome";

const FEATURES = [
  {
    icon: GitBranch,
    title: "Provenance and lineage",
    text: "See which datasets feed which analyses and results, and how each one changed along the way.",
  },
  {
    icon: FileCheck2,
    title: "Ethics and funding workflow",
    text: "Keep ethics approvals and funding steps in one place, with reminders before anything expires.",
  },
  {
    icon: Plug,
    title: "Integrations",
    text: "Link files and records from the tools your lab already uses, so they stay attached to the project.",
  },
  {
    icon: UserRoundCheck,
    title: "Handover",
    text: "When someone leaves, pass their projects and responsibilities to a colleague with a checklist.",
  },
];

/** Name on the left, theme and the two ways in on the right. Shown above every signed-out page. */
export function LandingHeader() {
  return (
    <header className="mx-auto flex w-full max-w-5xl items-center gap-3 px-4 py-4 md:px-8">
      <Link to="/" aria-label="labbenchos home">
        <img src={logo} alt="labbenchos" className="h-8 w-auto dark:hidden" />
        <img src={logoOnDark} alt="labbenchos" className="hidden h-8 w-auto dark:block" />
      </Link>
      <div className="ml-auto flex items-center gap-2">
        <ThemeToggle />
        <Button asChild variant="ghost">
          <Link to="/login">Sign in</Link>
        </Button>
        <Button asChild>
          <Link to="/signup">Register</Link>
        </Button>
      </div>
    </header>
  );
}

export function Features() {
  return (
    <section aria-label="What it does" className="grid gap-6 sm:grid-cols-2">
      {FEATURES.map(({ icon: Icon, title, text }) => (
        <div key={title} className="grid content-start gap-2 rounded-lg bg-muted p-6">
          <Icon className="size-6 text-primary" aria-hidden />
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="text-sm text-muted-foreground">{text}</p>
        </div>
      ))}
    </section>
  );
}

export function HeroText({ as: H = "p" }: { as?: "h1" | "p" }) {
  return (
    <div className="grid gap-4">
      <H className="text-4xl font-semibold tracking-tight text-balance md:text-5xl">
        Run your entire lab on one platform.
      </H>
      <p className="max-w-xl text-lg text-muted-foreground">
        From ethics approval and funding to experiments and publication, labbenchos connects every
        step of your research with the tools and AI your lab already uses.
      </p>
    </div>
  );
}

/** Signed-out home at "/": the labbenchos marketing page. Sign in leads into the app. */
export function LandingPage() {
  return <MarketingHome />;
}
