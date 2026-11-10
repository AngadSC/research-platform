import { Link, Outlet } from "react-router";
import logo from "@/assets/brand/labbenchos-logo.png";
import { Toaster } from "@/components/ui/sonner";
import "./auth-background.css";

/** Signed-out layout for sign in, create account and the other account pages: a slowly
 * moving light green and white background with the form in a card in the middle. */
export function AuthLayout() {
  return (
    <div className="auth-bg relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-12 text-foreground">
      <div className="auth-bg-blobs" aria-hidden="true">
        <span className="auth-blob auth-blob-1" />
        <span className="auth-blob auth-blob-2" />
        <span className="auth-blob auth-blob-3" />
        <span className="auth-blob auth-blob-4" />
      </div>
      <div className="relative z-10 grid w-full max-w-md gap-6">
        <Link to="/" aria-label="labbenchos home" className="justify-self-center">
          <img src={logo} alt="labbenchos" className="h-10 w-auto" />
        </Link>
        <main className="rounded-2xl border border-white/70 bg-card/90 p-8 shadow-xl shadow-green-900/10 backdrop-blur-md">
          <Outlet />
        </main>
        <Link
          to="/"
          className="justify-self-center text-sm font-medium text-slate-600 hover:text-slate-900"
        >
          ← Back to home
        </Link>
      </div>
      <Toaster />
    </div>
  );
}
