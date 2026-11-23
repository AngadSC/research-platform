import { Link, Outlet } from "react-router";
import logo from "@/assets/brand/labbenchos-logo.png";
import { Toaster } from "@/components/ui/sonner";
import "./auth-background.css";

/** Signed-out layout for sign in, create account and the other account pages: a calm
 * flat background with the form in a card in the middle. */
export function AuthLayout() {
  return (
    <div className="auth-bg relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-12 text-foreground">
      <div className="relative z-10 grid w-full max-w-md gap-6">
        <Link to="/" aria-label="labbenchos home" className="justify-self-center">
          <img src={logo} alt="labbenchos" className="h-10 w-auto" />
        </Link>
        <main className="glass glass--solid rounded-xl p-8 shadow-[var(--shadow-glass-2)]">
          <Outlet />
        </main>
        <Link
          to="/"
          className="justify-self-center text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          ← Back to home
        </Link>
      </div>
      <Toaster />
    </div>
  );
}
