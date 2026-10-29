"use client";

import { Cloud } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ThemeToggleIcon } from "@/components/ThemeToggleIcon";
import { AuthError } from "@/lib/auth";
import { OAuthButtons } from "@/components/OAuthButtons";

/* ============================================================================
   Shared chrome - duplicated from login page on purpose. Two short pages,
   one shared file isn't worth the indirection yet.
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

/* On /signup the right-hand CTA is "Sign in" (cross-link to /login). The
 * entire page IS the signup form, so a redundant "Get started" button in the
 * nav would be confusing. Same pattern as login but the buttons flip. */
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
   Signup form
   ========================================================================== */

export default function SignupPage() {
  const router = useRouter();
  const { register, login } = useAuth();

  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [errorKind, setErrorKind] = useState<"validation" | "exists" | "network">("validation");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

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
      await register(email.trim(), password, displayName.trim() || undefined);
      // Auto-login after successful registration.
      await login(email.trim(), password);
      router.push("/chat");
    } catch (err) {
      if (err instanceof AuthError) {
        // Backend sends the code REGISTER_USER_ALREADY_EXISTS (underscores).
        if (/already[ _]exists/i.test(err.message ?? "")) {
          setError("An account with that email already exists.");
          setErrorKind("exists");
        } else {
          setError(err.message || "Registration failed.");
          setErrorKind("validation");
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
              Create your workspace
            </h1>
            <p className="mt-2 text-sm text-[var(--fg-secondary)]">
              Your private AI platform &mdash; documents, sessions, and data are yours alone.
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
                  Display name{" "}
                  <span className="text-[var(--fg-muted)] normal-case font-normal tracking-normal">
                    (optional)
                  </span>
                </span>
                <input
                  type="text"
                  autoComplete="name"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  className="w-full px-3.5 py-2.5 text-sm bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-lg text-[var(--fg-primary)] placeholder-[var(--fg-muted)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent)]/20 focus:outline-none transition-all"
                  placeholder="Munir"
                />
              </label>

              <label className="block">
                <span className="text-xs font-medium text-[var(--fg-secondary)] mb-2 block uppercase tracking-wider">
                  Password
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
                  Confirm password
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
                    (errorKind === "exists"
                      ? "text-amber-700 dark:text-amber-300 bg-amber-500/10 border-amber-500/30"
                      : "text-red-500 bg-red-500/10 border-red-500/30")
                  }
                  role="alert"
                >
                  {error}
                  {errorKind === "exists" && (
                    <>
                      {" "}
                      <Link
                        href="/login"
                        className="underline underline-offset-2 hover:text-amber-600 dark:hover:text-amber-200"
                      >
                        Sign in instead?
                      </Link>
                    </>
                  )}
                </div>
              )}

              <button
                type="submit"
                disabled={submitting || !email || !password || !confirm}
                className="w-full py-2.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-bright)] text-white text-sm font-medium transition-all shadow-lg shadow-[var(--accent)]/20 disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none flex items-center justify-center gap-2"
              >
                {submitting ? (
                  <>
                    <span className="block w-3.5 h-3.5 rounded-full border-2 border-white/80 border-t-transparent animate-spin" />
                    Creating account...
                  </>
                ) : (
                  "Create account"
                )}
              </button>
              <OAuthButtons />
              <div className="text-center text-xs text-[var(--fg-tertiary)] pt-1">
                Already have an account?{" "}
                <Link
                  href="/login"
                  className="text-[var(--accent)] hover:text-[var(--accent-bright)] font-medium transition"
                >
                  Sign in
                </Link>
              </div>
            </form>
          </div>

          <div className="mt-6 text-center text-[0.65rem] font-mono uppercase tracking-wider text-[var(--fg-muted)]">
            private workspace &middot; per-user rag &middot; isolated by default
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