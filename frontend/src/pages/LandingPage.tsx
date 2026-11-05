import { FileCheck2, GitBranch, Plug, UserRoundCheck } from "lucide-react";
import { Link } from "react-router";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { Button } from "@/components/ui/button";
import { APP_NAME } from "@/lib/constants";

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
      <Link to="/" className="text-base font-semibold">
        {APP_NAME}
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
        Your lab&rsquo;s research, in one traceable place.
      </H>
      <p className="max-w-xl text-lg text-muted-foreground">
        Keep projects, documents, data files and results together, with a clear record of where
        everything came from and who approved it.
      </p>
    </div>
  );
}

/** Signed-out home at "/". */
export function LandingPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <LandingHeader />
      <main className="mx-auto grid max-w-5xl gap-16 px-4 py-16 md:px-8">
        <HeroText as="h1" />
        <div className="flex gap-3">
          <Button asChild size="lg">
            <Link to="/signup">Register</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link to="/login">Sign in</Link>
          </Button>
        </div>
        <Features />
      </main>
    </div>
  );
}
