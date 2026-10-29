"use client";

import { Cloud, MailCheck } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState, type FormEvent } from "react";

import { ThemeToggleIcon } from "@/components/ThemeToggleIcon";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ============================================================================
   Shared chrome - matches login/signup/forgot-password/reset-password.
   ========================================================================== */

function Wordmark() {
  return (
    <div className="inline-flex items-baseline gap-1.5">
      <Cloud className="w-5 h-5 text-[var(--accent)] self-center" strokeWidth={2.25} />
      <span
        className="text-xl font-bold bg-clip-text text-transparent tracking-tight"
        style={{ backgroundImage: "linear-gradient(135deg, var(--accent-bright), var(--accent))" }}
      >
        CloudNest
      </span>
      <span className="text-sm font-mono text-[var(--fg-tertiary)] opacity-70 -ml-1">.ai</span>
    </div>
  );
}

function AuthNav() {
  return (
    <nav className="sticky top-0 z-50 backdrop-blur-md bg-[var(--bg-base)]/80 border-b border-[var(--border-subtle)]">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link href="/" aria-label="CloudNest home">
          <Wordmark />
        </Link>
        <div className="flex items-center gap-3">
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
   Verify email: the link in the verification email lands here with ?token=.
   ========================================================================== */

type Status = "verifying" | "verified" | "invalid" | "network";

function VerifyEmail() {
  const token = useSearchParams().get("token") || "";
  const [status, setStatus] = useState<Status>(token ? "verifying" : "invalid");
  const started = useRef(false); // React strict mode runs effects twice in dev

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/verify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        if (res.ok) return setStatus("verified");
        const detail = (await res.json().catch(() => null))?.detail;
        // A second click on the same link is still a success for the user.
        setStatus(detail === "VERIFY_USER_ALREADY_VERIFIED" ? "verified" : "invalid");
      } catch {
        setStatus("network");
      }
    })();
  }, [token]);

  return (
    <div className="relative flex-1 flex items-center justify-center px-4 py-12">
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] rounded-full opacity-20 blur-3xl pointer-events-none"
        style={{ background: "radial-gradient(circle, var(--accent-bright) 0%, transparent 65%)" }}
      />
      <div className="relative w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold tracking-tight text-[var(--fg-primary)]">
            Verify your email
          </h1>
          <div
            className="mx-auto mt-4 h-[2px] w-20 rounded-full"
            style={{ background: "linear-gradient(90deg, transparent, var(--accent), transparent)" }}
          />
        </div>

        <div className="relative bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-2xl p-7 shadow-2xl text-center">
          {status === "verifying" && (
            <p className="text-sm text-[var(--fg-secondary)] flex items-center justify-center gap-2">
              <span className="block w-3.5 h-3.5 rounded-full border-2 border-[var(--accent)] border-t-transparent animate-spin" />
              Verifying your email...
            </p>
          )}

          {status === "verified" && (
            <>
              <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
                <MailCheck className="w-6 h-6 text-emerald-500" strokeWidth={2} />
              </div>
              <h2 className="text-base font-semibold text-[var(--fg-primary)] mb-2">
                Email verified
              </h2>
              <p className="text-sm text-[var(--fg-secondary)] leading-relaxed mb-5">
                Thanks for confirming your address.
              </p>
              <Link
                href="/chat"
                className="text-sm text-[var(--accent)] hover:text-[var(--accent-bright)] font-medium transition"
              >
                Continue to CloudNest
              </Link>
            </>
          )}

          {status === "network" && (
            <p className="text-sm text-red-500" role="alert">
              Network error. Please check your connection and reload this page.
            </p>
          )}

          {status === "invalid" && <ResendForm />}
        </div>
      </div>
    </div>
  );
}

/* Invalid, expired or missing token: let the user request a fresh link. The
 * API always answers 202 (no account enumeration), so the confirmation is
 * neutral. */
function ResendForm() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await fetch(`${API_BASE}/auth/request-verify-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
    } catch {
      /* neutral confirmation either way */
    } finally {
      setSubmitting(false);
      setSent(true);
    }
  };

  if (sent) {
    return (
      <p className="text-sm text-[var(--fg-secondary)] leading-relaxed">
        If that address belongs to an unverified account, a new verification link is on its way.
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 text-left">
      <p
        className="text-xs rounded-lg px-3 py-2.5 border text-amber-700 dark:text-amber-300 bg-amber-500/10 border-amber-500/30"
        role="alert"
      >
        This verification link is invalid or has expired. Enter your email to get a new one.
      </p>
      <input
        type="email"
        autoComplete="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@example.com"
        className="w-full px-3.5 py-2.5 text-sm bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-lg text-[var(--fg-primary)] placeholder-[var(--fg-muted)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent)]/20 focus:outline-none transition-all"
      />
      <button
        type="submit"
        disabled={submitting || !email.trim()}
        className="w-full py-2.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-bright)] text-white text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {submitting ? "Sending..." : "Send a new link"}
      </button>
    </form>
  );
}

/* useSearchParams() requires a Suspense boundary for static prerendering. */
export default function VerifyEmailPage() {
  return (
    <div className="min-h-screen flex flex-col bg-[var(--bg-base)]">
      <AuthNav />
      <Suspense fallback={null}>
        <VerifyEmail />
      </Suspense>
    </div>
  );
}
