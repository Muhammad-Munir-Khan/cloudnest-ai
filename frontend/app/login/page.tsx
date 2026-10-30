"use client";

import LogoMark from "@/components/LogoMark";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ThemeToggleIcon } from "@/components/ThemeToggleIcon";
import { AuthError } from "@/lib/auth";
import { safeRedirectPath } from "@/lib/redirect";
import { OAuthButtons } from "@/components/OAuthButtons";

/* ============================================================================
   Shared chrome
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

/* Full nav matching the landing page. On the login page, the right-hand
 * primary action is "Get started" (cross-link to /signup) since the entire
 * page IS the sign-in form. Same pattern Stripe/Linear use. */
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
            href="/signup"
            className="text-sm font-medium text-white bg-[var(--accent)] hover:bg-[var(--accent-bright)] transition px-4 py-1.5 rounded-md"
          >
            Get started
          </Link>
        </div>
      </div>
    </nav>
  );
}

/* ============================================================================
   Login form
   ========================================================================== */

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [errorKind, setErrorKind] = useState<"bad-creds" | "suspended" | "network">("bad-creds");
  const [submitting, setSubmitting] = useState(false);

  // Only same-origin paths: ?next= comes from the URL and could otherwise
  // send the user to another site after login (open redirect).
  const next = safeRedirectPath(searchParams.get("next"));
  const urlError = searchParams.get("error");

  /* If the user arrived with ?error=... in the URL (e.g. OAuth-suspended
   * redirect from the backend), surface it in the same banner the form uses.
   * We treat it as a "suspended" style by default since that's the only
   * scenario in our backend that does this redirect. */
  useEffect(() => {
    if (urlError) {
      setError(urlError);
      setErrorKind("suspended");
    }
  }, [urlError]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      router.push(next);
    } catch (err) {
      if (err instanceof AuthError) {
        if (err.status === 403) {
          setError(err.message || "Your account has been suspended.");
          setErrorKind("suspended");
        } else if (err.status === 400) {
          setError("Incorrect email or password.");
          setErrorKind("bad-creds");
        } else {
          setError(err.message || "Login failed.");
          setErrorKind("bad-creds");
        }
      } else {
        setError("Network error. Is the backend running?");
        setErrorKind("network");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
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
            Welcome back
          </h1>
          <p className="mt-2 text-sm text-[var(--fg-secondary)]">
            Sign in to your AI workspace.
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

            <label className="block">
              <span className="text-xs font-medium text-[var(--fg-secondary)] mb-2 block uppercase tracking-wider">
                Password
              </span>
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3.5 py-2.5 text-sm bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-lg text-[var(--fg-primary)] placeholder-[var(--fg-muted)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent)]/20 focus:outline-none transition-all"
                placeholder="********"
              />
            </label>

            {error && (
              <div
                className={
                  "text-xs rounded-lg px-3 py-2.5 border " +
                  (errorKind === "suspended"
                    ? "text-amber-700 dark:text-amber-300 bg-amber-500/10 border-amber-500/30"
                    : "text-red-500 bg-red-500/10 border-red-500/30")
                }
                role="alert"
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || !email || !password}
              className="w-full py-2.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-bright)] text-white text-sm font-medium transition-all shadow-lg shadow-[var(--accent)]/20 disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none flex items-center justify-center gap-2"
            >
              {submitting ? (
                <>
                  <span className="block w-3.5 h-3.5 rounded-full border-2 border-white/80 border-t-transparent animate-spin" />
                  Signing in...
                </>
              ) : (
                "Sign in"
              )}
            </button>
            <div className="text-right -mt-2">
              <Link
                href="/forgot-password"
                className="text-xs text-[var(--accent)] hover:text-[var(--accent-bright)] transition"
              >
                Forgot password?
              </Link>
            </div>
            <OAuthButtons />
            <div className="text-center text-xs text-[var(--fg-tertiary)] pt-1">
              New here?{" "}
              <Link
                href="/signup"
                className="text-[var(--accent)] hover:text-[var(--accent-bright)] font-medium transition"
              >
                Create an account
              </Link>
            </div>
          </form>
        </div>

        <div className="mt-6 text-center text-[0.65rem] font-mono uppercase tracking-wider text-[var(--fg-muted)]">
          secured by httpOnly cookies &middot; jwt &middot; postgres
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
  );
}

export default function LoginPage() {
  return (
    <div className="min-h-screen flex flex-col bg-[var(--bg-base)]">
      <AuthNav />
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </div>
  );
}