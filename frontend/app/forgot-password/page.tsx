"use client";

import LogoMark from "@/components/LogoMark";
import { MailCheck } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { ThemeToggleIcon } from "@/components/ThemeToggleIcon";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

/* ============================================================================
   Shared chrome - duplicated from login/signup. Three small files, one shared
   abstraction isn't worth the indirection yet.
   ========================================================================== */

function Wordmark({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizes = {
    sm: { text: "text-base", tld: "text-[0.7rem]", icon: "w-5 h-5" },
    md: { text: "text-lg", tld: "text-xs", icon: "w-6 h-6" },
    lg: { text: "text-xl", tld: "text-sm", icon: "w-5 h-5" },
  };
  const s = sizes[size];
  return (
    <div className="inline-flex items-baseline gap-1.5">
      <LogoMark className={`${s.icon} self-center shrink-0`} />
      <span
        className={`${s.text} font-bold bg-clip-text text-transparent tracking-tight`}
        style={{ backgroundImage: "linear-gradient(135deg, var(--accent-bright), var(--accent))" }}
      >
        CloudNest
      </span>
      <span className={`${s.tld} font-mono text-[var(--fg-tertiary)] opacity-70 -ml-1`}>.ai</span>
    </div>
  );
}

/* On /forgot-password the right-hand CTA is "Sign in" - that's where the user
 * came from and where they'll go next (either after getting the reset email,
 * or if they remembered their password mid-flow). Same nav as /signup. */
function AuthNav() {
  return (
    <nav className="sticky top-0 z-50 backdrop-blur-md bg-[var(--bg-base)]/80 border-b border-[var(--border-subtle)]">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link href="/" aria-label="CloudNest home">
          <Wordmark size="lg" />
        </Link>
        <div className="flex items-center gap-3">
          <Link
            href="/#features"
            className="hidden md:inline text-sm text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] transition px-3 py-1.5"
          >
            Features
          </Link>
          <Link
            href="/#use-cases"
            className="hidden md:inline text-sm text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] transition px-3 py-1.5"
          >
            Use cases
          </Link>
          <Link
            href="/#stack"
            className="hidden md:inline text-sm text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] transition px-3 py-1.5"
          >
            Stack
          </Link>
          <ThemeToggleIcon />
          <Link
            href="/login"
            className="text-sm font-medium text-[var(--fg-primary)] border border-[var(--border-subtle)] hover:border-[var(--accent)]/40 transition px-4 py-1.5 rounded-md"
          >
            Sign in
          </Link>
        </div>
      </div>
    </nav>
  );
}

/* ============================================================================
   Forgot password page
   ========================================================================== */

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      // fastapi-users returns 202 regardless of whether the email exists
      // (no user enumeration). We show the same confirmation either way.
      await fetch(`${API_BASE}/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
    } catch {
      // Even on network error we show the neutral confirmation; the user
      // can retry. We deliberately don't reveal backend state.
    } finally {
      setSubmitting(false);
      setDone(true);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-[var(--bg-base)]">
      <AuthNav />

      <div className="relative flex-1 flex items-center justify-center px-4 py-12">
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] rounded-full opacity-20 blur-3xl pointer-events-none"
          style={{ background: "radial-gradient(circle, var(--accent-bright) 0%, transparent 65%)" }}
        />
        <div
          className="absolute inset-0 opacity-[0.025] pointer-events-none"
          style={{
            backgroundImage:
              "linear-gradient(var(--fg-primary) 1px, transparent 1px), linear-gradient(90deg, var(--fg-primary) 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />

        <div className="relative w-full max-w-md fade-in-mount">
          <div className="mb-8 text-center">
            <h1 className="text-3xl font-bold tracking-tight text-[var(--fg-primary)]">
              Forgot your password?
            </h1>
            <p className="mt-2 text-sm text-[var(--fg-secondary)]">
              Enter your email and we&apos;ll send you a reset link.
            </p>
            <div
              className="mx-auto mt-4 h-[2px] w-20 rounded-full"
              style={{ background: "linear-gradient(90deg, transparent, var(--accent), transparent)" }}
            />
          </div>

          <div className="relative">
            <div
              className="absolute inset-0 rounded-2xl opacity-30 blur-xl pointer-events-none"
              style={{ background: "linear-gradient(135deg, var(--accent-bright), var(--accent))" }}
            />

            {done ? (
              <div className="relative bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-2xl p-7 shadow-2xl text-center">
                <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
                  <MailCheck className="w-6 h-6 text-emerald-500" strokeWidth={2} />
                </div>
                <h2 className="text-base font-semibold text-[var(--fg-primary)] mb-2">
                  Check your email
                </h2>
                <p className="text-sm text-[var(--fg-secondary)] leading-relaxed mb-5">
                  If an account exists for{" "}
                  <span className="text-[var(--fg-primary)] font-medium">
                    {email}
                  </span>
                  , you&apos;ll receive a password reset link shortly. The link
                  expires in 1 hour.
                </p>
                <Link
                  href="/login"
                  className="inline-flex items-center gap-1.5 text-sm text-[var(--accent)] hover:text-[var(--accent-bright)] font-medium transition"
                >
                  Back to sign in
                </Link>
              </div>
            ) : (
              <form
                onSubmit={handleSubmit}
                className="relative bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-2xl p-7 space-y-5 shadow-2xl"
              >
                <label className="block">
                  <span className="text-xs font-medium text-[var(--fg-secondary)] mb-2 block uppercase tracking-wider">
                    Email
                  </span>
                  <input
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-3.5 py-2.5 text-sm bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-lg text-[var(--fg-primary)] placeholder-[var(--fg-muted)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent)]/20 focus:outline-none transition-all"
                    placeholder="you@example.com"
                  />
                </label>

                <button
                  type="submit"
                  disabled={submitting || !email}
                  className="w-full py-2.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-bright)] text-white text-sm font-medium transition-all shadow-lg shadow-[var(--accent)]/20 disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none flex items-center justify-center gap-2"
                >
                  {submitting ? (
                    <>
                      <span className="block w-3.5 h-3.5 rounded-full border-2 border-white/80 border-t-transparent animate-spin" />
                      Sending...
                    </>
                  ) : (
                    "Send reset link"
                  )}
                </button>

                <div className="text-center text-xs text-[var(--fg-tertiary)] pt-1">
                  Remember it?{" "}
                  <Link
                    href="/login"
                    className="text-[var(--accent)] hover:text-[var(--accent-bright)] font-medium transition"
                  >
                    Back to sign in
                  </Link>
                </div>
              </form>
            )}
          </div>

          <div className="mt-6 text-center text-[0.65rem] font-mono uppercase tracking-wider text-[var(--fg-muted)]">
            no enumeration &middot; one-hour token &middot; signed jwt
          </div>
        </div>

        <style jsx>{`
          @keyframes fade-in-mount {
            from { opacity: 0; transform: translateY(8px); }
            to   { opacity: 1; transform: translateY(0); }
          }
          .fade-in-mount {
            animation: fade-in-mount 0.5s ease-out;
          }
        `}</style>
      </div>
    </div>
  );
}