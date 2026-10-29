"use client";

import { Cloud, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { ThemeToggleIcon } from "@/components/ThemeToggleIcon";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ============================================================================
   Shared chrome - matches login/signup/forgot-password.
   ========================================================================== */

function Wordmark({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizes = {
    sm: { text: "text-base", tld: "text-[0.7rem]", icon: "w-4 h-4" },
    md: { text: "text-lg", tld: "text-xs", icon: "w-[18px] h-[18px]" },
    lg: { text: "text-xl", tld: "text-sm", icon: "w-5 h-5" },
  };
  const s = sizes[size];
  return (
    <div className="inline-flex items-baseline gap-1.5">
      <Cloud className={`${s.icon} text-[var(--accent)] self-center`} strokeWidth={2.25} />
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

/* On /reset-password the right-hand CTA is "Sign in" - that's where the user
 * lands after a successful reset. Same nav as /signup and /forgot-password. */
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
   Reset password form
   ========================================================================== */

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [errorKind, setErrorKind] = useState<"validation" | "bad-token" | "network">("validation");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!token) {
      setError("Missing or invalid reset link. Please request a new one.");
      setErrorKind("bad-token");
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match.");
      setErrorKind("validation");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      setErrorKind("validation");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });

      if (res.ok) {
        setDone(true);
        setTimeout(() => router.push("/login"), 2500);
      } else {
        const data = await res.json().catch(() => null);
        const reason = data?.detail;
        if (typeof reason === "string" && reason.includes("RESET_PASSWORD_BAD_TOKEN")) {
          setError("This reset link is invalid or has expired. Request a new one.");
          setErrorKind("bad-token");
        } else if (reason?.code === "RESET_PASSWORD_INVALID_PASSWORD") {
          // Server-side password policy: {code, reason}.
          setError(
            typeof reason.reason === "string"
              ? reason.reason
              : "Password doesn't meet requirements.",
          );
          setErrorKind("validation");
        } else if (typeof reason === "string" && reason.includes("PASSWORD")) {
          setError("Password doesn't meet requirements. Use at least 8 characters.");
          setErrorKind("validation");
        } else {
          setError("This reset link is invalid or has expired. Request a new one.");
          setErrorKind("bad-token");
        }
      }
    } catch {
      setError("Network error. Is the backend running?");
      setErrorKind("network");
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
            Set a new password
          </h1>
          <p className="mt-2 text-sm text-[var(--fg-secondary)]">
            Choose a strong password for your account.
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
                <ShieldCheck className="w-6 h-6 text-emerald-500" strokeWidth={2} />
              </div>
              <h2 className="text-base font-semibold text-[var(--fg-primary)] mb-2">
                Password updated
              </h2>
              <p className="text-sm text-[var(--fg-secondary)] leading-relaxed mb-5">
                Your password has been reset. Redirecting you to sign in...
              </p>
              <Link
                href="/login"
                className="text-sm text-[var(--accent)] hover:text-[var(--accent-bright)] font-medium transition"
              >
                Sign in now
              </Link>
            </div>
          ) : (
            <form
              onSubmit={handleSubmit}
              className="relative bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-2xl p-7 space-y-5 shadow-2xl"
            >
              <label className="block">
                <span className="text-xs font-medium text-[var(--fg-secondary)] mb-2 block uppercase tracking-wider">
                  New password
                </span>
                <input
                  type="password"
                  autoComplete="new-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3.5 py-2.5 text-sm bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-lg text-[var(--fg-primary)] placeholder-[var(--fg-muted)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent)]/20 focus:outline-none transition-all"
                  placeholder="at least 8 characters"
                />
              </label>

              <label className="block">
                <span className="text-xs font-medium text-[var(--fg-secondary)] mb-2 block uppercase tracking-wider">
                  Confirm new password
                </span>
                <input
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="w-full px-3.5 py-2.5 text-sm bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-lg text-[var(--fg-primary)] placeholder-[var(--fg-muted)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent)]/20 focus:outline-none transition-all"
                  placeholder="********"
                />
              </label>

              {error && (
                <div
                  className={
                    "text-xs rounded-lg px-3 py-2.5 border " +
                    (errorKind === "bad-token"
                      ? "text-amber-700 dark:text-amber-300 bg-amber-500/10 border-amber-500/30"
                      : "text-red-500 bg-red-500/10 border-red-500/30")
                  }
                  role="alert"
                >
                  {error}
                  {errorKind === "bad-token" && (
                    <>
                      {" "}
                      <Link
                        href="/forgot-password"
                        className="underline underline-offset-2 hover:text-amber-600 dark:hover:text-amber-200"
                      >
                        Request a new link
                      </Link>
                    </>
                  )}
                </div>
              )}

              <button
                type="submit"
                disabled={submitting || !password || !confirm}
                className="w-full py-2.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-bright)] text-white text-sm font-medium transition-all shadow-lg shadow-[var(--accent)]/20 disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none flex items-center justify-center gap-2"
              >
                {submitting ? (
                  <>
                    <span className="block w-3.5 h-3.5 rounded-full border-2 border-white/80 border-t-transparent animate-spin" />
                    Updating...
                  </>
                ) : (
                  "Update password"
                )}
              </button>

              <div className="text-center text-xs text-[var(--fg-tertiary)] pt-1">
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
          one-time token &middot; one-hour expiry &middot; bcrypt hashed
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

/* useSearchParams() requires a Suspense boundary in Next.js production builds.
 * The page export wraps the form in Suspense so static prerendering succeeds. */
export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen flex flex-col bg-[var(--bg-base)]">
      <AuthNav />
      <Suspense fallback={null}>
        <ResetPasswordForm />
      </Suspense>
    </div>
  );
}