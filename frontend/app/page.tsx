"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Boxes,
  Building2,
  Cloud,
  Container,
  Database,
  Eye,
  FileText,
  Gavel,
  Globe,
  GraduationCap,
  Github,
  HeartPulse,
  Layers,
  LineChart,
  Lock,
  Network,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
  Wrench,
  Zap,
} from "lucide-react";

import { useAuth } from "@/components/AuthProvider";
import { ThemeToggleIcon } from "@/components/ThemeToggleIcon";

/* ============================================================================
   Custom keyframes + helpers injected once via a style tag at top of <body>.
   Keeping everything CSS-driven means zero animation libraries shipped.
   ========================================================================== */
const PAGE_STYLES = `
@keyframes shimmer-line {
  0%   { transform: translateX(-100%); opacity: 0; }
  50%  { opacity: 1; }
  100% { transform: translateX(100%); opacity: 0; }
}
@keyframes float-y {
  0%, 100% { transform: translateY(0px); }
  50%      { transform: translateY(-6px); }
}
@keyframes fade-up {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes pulse-soft {
  0%, 100% { opacity: 0.6; }
  50%      { opacity: 1; }
}
@keyframes draw-stroke {
  from { stroke-dashoffset: 100%; }
  to   { stroke-dashoffset: 0; }
}
@keyframes blink-caret {
  0%, 49%   { opacity: 1; }
  50%, 100% { opacity: 0; }
}
@keyframes type-in {
  from { width: 0; }
  to   { width: 100%; }
}
.reveal-init { opacity: 0; transform: translateY(20px); transition: opacity 0.7s ease-out, transform 0.7s ease-out; }
.reveal-on   { opacity: 1; transform: translateY(0); }
.shimmer-bar {
  position: relative; overflow: hidden;
}
.shimmer-bar::after {
  content: ""; position: absolute; inset: 0;
  background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.4) 50%, transparent 100%);
  animation: shimmer-line 2.6s ease-in-out infinite;
}
.float-soft { animation: float-y 5s ease-in-out infinite; }
.pulse-soft { animation: pulse-soft 2.4s ease-in-out infinite; }
.caret { animation: blink-caret 1s steps(1) infinite; }
@media (max-width: 768px) {
  .float-soft, .shimmer-bar::after { animation: none !important; }
}
`;

export default function LandingPage() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading && user) router.replace("/chat");
  }, [loading, user, router]);

  /* Set up IntersectionObserver once for all .reveal-init elements */
  useEffect(() => {
    const els = document.querySelectorAll<HTMLElement>(".reveal-init");
    if (!("IntersectionObserver" in window)) {
      els.forEach((el) => el.classList.add("reveal-on"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("reveal-on");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--fg-primary)]">
      <style dangerouslySetInnerHTML={{ __html: PAGE_STYLES }} />
      <TopNav />
      <Hero />
      <NumbersBar />
      <Features />
      <ArchitectureViz />
      <BuiltForTeams />
      <UseCases />
      <ProviderSwitchDemo />
      <HowItWorks />
      <TechStack />
      <FinalCTA />
      <SiteFooter />
    </div>
  );
}

/* ============================================================================
   Wordmark / nav
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

function TopNav() {
  return (
    <nav className="sticky top-0 z-50 backdrop-blur-md bg-[var(--bg-base)]/80 border-b border-[var(--border-subtle)]">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link href="/" aria-label="CloudNest home">
          <Wordmark size="lg" />
        </Link>
        <div className="flex items-center gap-3">
          <a href="#features" className="hidden md:inline text-sm text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] transition px-3 py-1.5">Features</a>
          <a href="#architecture" className="hidden md:inline text-sm text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] transition px-3 py-1.5">How it works</a>
          <a href="#use-cases" className="hidden md:inline text-sm text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] transition px-3 py-1.5">Use cases</a>
          <a href="#stack" className="hidden md:inline text-sm text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] transition px-3 py-1.5">Stack</a>
          <ThemeToggleIcon />
          <Link href="/login" className="text-sm text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] transition px-3 py-1.5">Sign in</Link>
          <Link href="/signup" className="text-sm font-medium text-white bg-[var(--accent)] hover:bg-[var(--accent-bright)] transition px-4 py-1.5 rounded-md">Get started</Link>
        </div>
      </div>
    </nav>
  );
}

/* ============================================================================
   Hero — refined, with a self-typing chat panel
   ========================================================================== */
function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div
        className="absolute -top-40 left-1/2 -translate-x-1/2 w-[1100px] h-[1100px] rounded-full opacity-20 blur-3xl pointer-events-none"
        style={{ background: "radial-gradient(circle, var(--accent-bright) 0%, transparent 60%)" }}
      />
      <div
        className="absolute inset-0 opacity-[0.025] pointer-events-none"
        style={{
          backgroundImage:
            "linear-gradient(var(--fg-primary) 1px, transparent 1px), linear-gradient(90deg, var(--fg-primary) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
        }}
      />

      <div className="relative max-w-6xl mx-auto px-6 pt-20 pb-16 md:pt-28 md:pb-24">
        <div className="grid md:grid-cols-2 gap-12 items-center">
          <div className="reveal-init">
            <div className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-[var(--fg-tertiary)] bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-full px-3 py-1 mb-6">
              <span className="block w-1.5 h-1.5 rounded-full bg-emerald-500 pulse-soft" />
              Self-hostable &middot; Multi-tenant &middot; Production-ready
            </div>

            <h1 className="text-4xl md:text-5xl lg:text-[3.4rem] font-bold tracking-tight leading-[1.03] mb-5">
              Your own{" "}
              <span
                className="bg-clip-text text-transparent"
                style={{ backgroundImage: "linear-gradient(135deg, var(--accent-bright), var(--accent))" }}
              >
                AI workspace
              </span>
              . Your data. Your rules.
            </h1>

            <div
              className="h-[2px] w-32 mb-6 shimmer-bar rounded-full"
              style={{ background: "linear-gradient(90deg, transparent, var(--accent), transparent)" }}
            />

            <p className="text-base md:text-lg text-[var(--fg-secondary)] leading-relaxed mb-8 max-w-lg">
              A complete conversational AI platform you run yourself. Per-user
              RAG, tool-using agents, a curated knowledge base, voice, vision,
              and true multilingual retrieval across 100+ languages. Switch
              LLM providers with one config line. Deploy with one Docker
              command.
            </p>

            <div className="flex flex-wrap gap-3">
              <Link
                href="/signup"
                className="group inline-flex items-center gap-2 px-5 py-2.5 rounded-md bg-[var(--accent)] hover:bg-[var(--accent-bright)] text-white text-sm font-medium transition-all shadow-lg shadow-[var(--accent)]/20 hover:shadow-xl hover:shadow-[var(--accent)]/30 hover:-translate-y-0.5"
              >
                Create your workspace
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
              </Link>
              <a
                href="#architecture"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md border border-[var(--border-subtle)] hover:border-[var(--accent)]/40 text-[var(--fg-primary)] text-sm font-medium transition"
              >
                See how it works
              </a>
            </div>

            <div className="mt-10 flex flex-wrap gap-6 text-xs text-[var(--fg-tertiary)]">
              <div className="flex items-center gap-2"><ShieldCheck className="w-3.5 h-3.5 text-[var(--accent)]" />Strict tenant isolation</div>
              <div className="flex items-center gap-2"><Globe className="w-3.5 h-3.5 text-[var(--accent)]" />100+ languages</div>
              <div className="flex items-center gap-2"><Container className="w-3.5 h-3.5 text-[var(--accent)]" />Docker-native</div>
            </div>
          </div>

          <div className="relative reveal-init">
            <TypingChatMock />
          </div>
        </div>
      </div>
    </section>
  );
}

/* ============================================================================
   Self-typing chat mock — runs once, loops every ~14s
   No real LLM call. Visually demonstrates streaming + dual-corpus retrieval.
   ========================================================================== */
function TypingChatMock() {
  const [stage, setStage] = useState(0);
  const [typed, setTyped] = useState("");
  const fullAnswer =
    "Per the remote work policy, employees may work remotely up to 4 days per week with manager approval. Based on your time-off balance, you have 12 vacation days remaining for the year.";

  useEffect(() => {
    // stages: 0 = user typing, 1 = tools running, 2 = answer streaming, 3 = done & sources
    let mounted = true;
    const run = async () => {
      while (mounted) {
        setStage(0);
        setTyped("");
        await wait(700);
        setStage(1);
        await wait(1600);
        setStage(2);
        for (let i = 0; i <= fullAnswer.length; i++) {
          if (!mounted) return;
          setTyped(fullAnswer.slice(0, i));
          await wait(14 + Math.random() * 18);
        }
        setStage(3);
        await wait(5000);
      }
    };
    run();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="relative">
      <div
        className="absolute inset-0 rounded-2xl opacity-50 blur-2xl pointer-events-none"
        style={{ background: "linear-gradient(135deg, var(--accent-bright), var(--accent))" }}
      />

      <div className="relative bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-2xl shadow-2xl overflow-hidden float-soft">
        <div className="flex items-center gap-1.5 px-4 py-3 border-b border-[var(--border-subtle)] bg-[var(--bg-sidebar)]">
          <div className="w-2.5 h-2.5 rounded-full bg-red-400/60" />
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-400/60" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-400/60" />
          <div className="ml-3 text-[0.65rem] font-mono text-[var(--fg-tertiary)]">cloudnest / chat</div>
          <div className="ml-auto text-[0.6rem] font-mono text-emerald-500 flex items-center gap-1.5">
            <span className="block w-1.5 h-1.5 rounded-full bg-emerald-500 pulse-soft" />
            live
          </div>
        </div>

        <div className="p-5 space-y-4 text-sm min-h-[300px]">
          <div className="flex gap-3">
            <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-xs font-semibold text-white bg-gradient-to-br from-slate-500 to-slate-700">U</div>
            <div className="flex-1 text-[var(--fg-primary)] pt-1">
              Summarize our remote work policy and tell me how many vacation days I have left.
            </div>
          </div>

          {stage >= 1 && (
            <div className="ml-10 flex flex-wrap gap-1.5" style={{ animation: "fade-up 0.4s ease-out" }}>
              <ToolPill name="knowledge_base_search" done={stage >= 2} />
              <ToolPill name="document_search" done={stage >= 2} />
              <ToolPill name="calculator" done={stage >= 2} />
            </div>
          )}

          {stage >= 2 && (
            <div className="flex gap-3" style={{ animation: "fade-up 0.4s ease-out" }}>
              <div
                className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-white"
                style={{ background: "linear-gradient(135deg, var(--accent-bright), var(--accent))" }}
              >
                <Cloud className="w-3.5 h-3.5" strokeWidth={2.5} />
              </div>
              <div className="flex-1 pt-1">
                <div className="text-[var(--fg-primary)] leading-relaxed">
                  {typed}
                  {stage === 2 && <span className="caret inline-block w-[2px] h-[14px] bg-[var(--accent)] align-middle ml-0.5" />}
                </div>

                {stage >= 3 && (
                  <div className="mt-3 flex flex-wrap gap-2 text-[0.65rem] font-mono" style={{ animation: "fade-up 0.4s ease-out" }}>
                    <span className="inline-flex items-center gap-1.5 text-amber-700 dark:text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-full px-2.5 py-1">
                      <Layers className="w-3 h-3" />
                      KB · remote_work_policy.pdf
                    </span>
                    <span className="inline-flex items-center gap-1.5 text-[var(--fg-tertiary)] bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-full px-2.5 py-1">
                      <FileText className="w-3 h-3" />
                      personal · time_off_balance.docx
                    </span>
                    <span className="inline-flex items-center gap-1.5 text-[var(--fg-tertiary)] bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-full px-2.5 py-1">
                      <Zap className="w-3 h-3" />
                      1.4s
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ToolPill({ name, done }: { name: string; done: boolean }) {
  return (
    <div className="inline-flex items-center gap-1.5 text-[0.65rem] font-mono px-2 py-0.5 rounded bg-[var(--bg-base)] border border-[var(--border-subtle)]">
      <span className="text-[var(--fg-secondary)]">{name}</span>
      <span
        className={done ? "text-emerald-500" : "text-amber-500"}
        style={{ animation: done ? "none" : "pulse-soft 1s ease-in-out infinite" }}
      >
        {done ? "●" : "○"}
      </span>
    </div>
  );
}

function wait(ms: number) {
  return new Promise<void>((r) => setTimeout(r, ms));
}

/* ============================================================================
   Numbers bar — animated counters, big single moment of impact
   ========================================================================== */
function NumbersBar() {
  const targets = [
    { v: 10, label: "agent tools", suffix: "" },
    { v: 100, label: "languages", suffix: "+" },
    { v: 3, label: "LLM providers", suffix: "" },
    { v: 49, label: "API endpoints", suffix: "" },
  ];
  return (
    <section className="border-y border-[var(--border-subtle)] bg-[var(--bg-sidebar)]/30">
      <div className="max-w-6xl mx-auto px-6 py-12">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {targets.map((t) => (
            <Counter key={t.label} target={t.v} suffix={t.suffix} label={t.label} />
          ))}
        </div>
      </div>
    </section>
  );
}

function Counter({ target, suffix, label }: { target: number; suffix: string; label: string }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [val, setVal] = useState(0);

  useEffect(() => {
    if (!ref.current) return;
    let started = false;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !started) {
          started = true;
          const duration = 1500;
          const start = performance.now();
          const tick = (now: number) => {
            const t = Math.min(1, (now - start) / duration);
            const eased = 1 - Math.pow(1 - t, 3);
            setVal(Math.round(eased * target));
            if (t < 1) requestAnimationFrame(tick);
          };
          requestAnimationFrame(tick);
        }
      },
      { threshold: 0.4 },
    );
    io.observe(ref.current);
    return () => io.disconnect();
  }, [target]);

  return (
    <div ref={ref} className="text-center">
      <div
        className="text-4xl md:text-5xl font-bold tracking-tight bg-clip-text text-transparent tabular-nums"
        style={{ backgroundImage: "linear-gradient(135deg, var(--accent-bright), var(--accent))" }}
      >
        {val}
        {suffix}
      </div>
      <div className="text-[0.65rem] font-mono uppercase tracking-wider text-[var(--fg-tertiary)] mt-2">{label}</div>
    </div>
  );
}

/* ============================================================================
   Features grid — content unchanged but cards gain hover lift + accent border
   ========================================================================== */
const FEATURES = [
  { icon: FileText, title: "Per-user RAG", body: "Every user gets a private Weaviate tenant. Upload PDFs, DOCX, text, or Markdown. Citations show source filenames and page numbers. One user cannot see another user's data - enforced at the storage layer, not just the application." },
  { icon: Layers, title: "Shared knowledge base", body: "A curated corpus that everyone in your workspace can read but only admins can write. Upload policies, manuals, FAQs once. Citations distinguish personal documents from the shared knowledge base with visual badges." },
  { icon: ShieldCheck, title: "Admin panel", body: "Three-tier roles: user, corpus_admin, super_admin. Manage users, suspend accounts (with email notification + reason), reset passwords, force-logout active sessions instantly. Curate the shared KB. Live system stats." },
  { icon: Wrench, title: "10 agent tools", body: "Personal document search, shared KB search, document summarizer, web search, calculator, JSON parser, datetime helper, unit converter, currency converter (live ECB rates), live weather. Powered by a LangGraph ReAct loop." },
  { icon: Sparkles, title: "Multi-LLM ensemble", body: "Fan out a question to three models in parallel; a judge model ranks them and synthesizes the best answer. Real model comparison with explainable rankings - useful when accuracy matters more than latency." },
  { icon: Eye, title: "Vision + voice", body: "Vision model reads images and scanned PDFs when text extraction falls short. Whisper for speech-to-text. Edge TTS for multilingual voice output across 37 native voices." },
  { icon: Globe, title: "Multilingual retrieval", body: "Powered by BAAI/bge-m3, a state-of-the-art multilingual embedding model. Upload a manual in English, query it in Urdu - cross-lingual retrieval works because the embeddings share semantic space across 100+ languages." },
  { icon: Lock, title: "Production-grade security", body: "JWT plus httpOnly cookies (XSS-resistant). OAuth via Google and GitHub. Force-logout invalidates active sessions on the next request, globally. Account suspension with email notifications and audit-friendly admin logging." },
  { icon: LineChart, title: "Built-in observability", body: "Every agent run is traced via Langfuse: tool calls, latencies, tokens, costs. Filter by user or session. Debug bad answers by replaying the exact tool tree the agent followed." },
];

function Features() {
  return (
    <section id="features" className="relative py-20 md:py-28 border-t border-[var(--border-subtle)]">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-14 reveal-init">
          <div className="text-xs font-mono uppercase tracking-wider text-[var(--accent)] mb-3">Everything that matters</div>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight">A complete platform, not a chat wrapper.</h2>
          <p className="text-[var(--fg-secondary)] mt-3 max-w-xl mx-auto">
            Every feature in CloudNest works end-to-end. Every endpoint requires authentication. Every user sees only their own data.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((f, i) => (
            <FeatureCard key={f.title} icon={f.icon} title={f.title} body={f.body} delay={i * 40} />
          ))}
        </div>
      </div>
    </section>
  );
}

function FeatureCard({
  icon: Icon,
  title,
  body,
  delay,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
  delay: number;
}) {
  return (
    <div
      className="reveal-init group relative p-6 rounded-xl bg-[var(--bg-card)] border border-[var(--border-subtle)] hover:border-[var(--accent)]/40 hover:-translate-y-1 transition-all duration-300"
      style={{ transitionDelay: `${delay}ms` }}
    >
      <div
        className="absolute inset-x-0 -top-px h-px opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ background: "linear-gradient(90deg, transparent, var(--accent), transparent)" }}
      />
      <div className="w-10 h-10 rounded-lg flex items-center justify-center mb-4 bg-[var(--accent-soft)] border border-[var(--border-subtle)] group-hover:bg-[var(--accent)]/15 transition-colors">
        <Icon className="w-5 h-5 text-[var(--accent)]" />
      </div>
      <h3 className="text-base font-semibold text-[var(--fg-primary)] mb-2">{title}</h3>
      <p className="text-sm text-[var(--fg-secondary)] leading-relaxed">{body}</p>
    </div>
  );
}

/* ============================================================================
   Architecture Viz - layered stack with animated request trace
   The standout "wow" moment.
   ========================================================================== */
function ArchitectureViz() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [traceActive, setTraceActive] = useState(false);

  useEffect(() => {
    if (!ref.current) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setRevealed(true);
          // Start the request-trace loop after layers settle in
          setTimeout(() => setTraceActive(true), 1400);
          io.disconnect();
        }
      },
      { threshold: 0.25 },
    );
    io.observe(ref.current);
    return () => io.disconnect();
  }, []);

  return (
    <section
      id="architecture"
      className="py-20 md:py-28 border-t border-[var(--border-subtle)] bg-[var(--bg-sidebar)]/20 relative overflow-hidden"
    >
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2 w-[900px] h-[900px] rounded-full opacity-[0.07] blur-3xl pointer-events-none"
        style={{ background: "radial-gradient(circle, var(--accent-bright) 0%, transparent 65%)" }}
      />

      <div className="max-w-6xl mx-auto px-6 relative">
        <div className="text-center mb-12 reveal-init">
          <div className="text-xs font-mono uppercase tracking-wider text-[var(--accent)] mb-3">
            Under the hood
          </div>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
            Watch a request travel through the stack.
          </h2>
          <p className="text-[var(--fg-secondary)] mt-3 max-w-xl mx-auto">
            Five layers. Deliberate boundaries. Strict isolation enforced at the
            storage layer, not just the application. The glowing dot is a real
            request flowing through the system on every chat message.
          </p>
        </div>

        <div
          ref={ref}
          className="relative bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-2xl p-6 md:p-10 reveal-init"
        >
          <LayeredStack revealed={revealed} traceActive={traceActive} />

          <div className="mt-10 grid md:grid-cols-3 gap-4 text-sm">
            <ArchInsight
              num="01"
              title="Authenticated entry, no exceptions"
              body="Every request carries a JWT (cookie or bearer). The auth dependency verifies signature, expiry, AND a force-logout iat-cutoff on every call - including chat, RAG, voice, and admin."
            />
            <ArchInsight
              num="02"
              title="Per-user isolation at the storage layer"
              body="Each user gets a dedicated Weaviate tenant. A contextvar carries their UUID through the agent loop. Cross-user data leakage is structurally impossible, not just policy-impossible."
            />
            <ArchInsight
              num="03"
              title="Two distinct retrieval tools"
              body="document_search reaches the user's tenant. knowledge_base_search reaches the admin-curated shared corpus. Tools do not overlap, so the agent never thrashes between them."
            />
          </div>
        </div>
      </div>
    </section>
  );
}

interface LayerComponent {
  label: string;
  sub: string;
}

interface ArchLayer {
  key: string;
  title: string;
  subtitle: string;
  components: LayerComponent[];
  highlight: string;
  color: string;
}

const ARCH_LAYERS: ArchLayer[] = [
  {
    key: "client",
    title: "Client",
    subtitle: "Browser, mobile, CLI",
    components: [
      { label: "Next.js 15", sub: "streaming UI" },
      { label: "OAuth", sub: "Google / GitHub" },
      { label: "REST + SSE", sub: "API clients" },
    ],
    highlight: "User initiates a chat message",
    color: "from-cyan-500/10 to-cyan-500/5",
  },
  {
    key: "edge",
    title: "Edge / API",
    subtitle: "FastAPI · auth · routes",
    components: [
      { label: "JWT verify", sub: "iat cutoff" },
      { label: "CORS + cookies", sub: "httpOnly" },
      { label: "49 endpoints", sub: "OpenAPI" },
    ],
    highlight: "Auth dependency runs the freshness check",
    color: "from-blue-500/10 to-blue-500/5",
  },
  {
    key: "agent",
    title: "Agent",
    subtitle: "LangGraph ReAct loop",
    components: [
      { label: "10 tools", sub: "scoped" },
      { label: "memory window", sub: "10 turns" },
      { label: "SSE streaming", sub: "live trace" },
    ],
    highlight: "Tool calls execute, results synthesized",
    color: "from-violet-500/10 to-violet-500/5",
  },
  {
    key: "retrieval",
    title: "Retrieval",
    subtitle: "Weaviate · BGE-M3",
    components: [
      { label: "Per-user tenant", sub: "isolated" },
      { label: "Shared KB", sub: "admin curated" },
      { label: "Hybrid search", sub: "BM25 + vector" },
    ],
    highlight: "Cross-lingual semantic search runs",
    color: "from-emerald-500/10 to-emerald-500/5",
  },
  {
    key: "storage",
    title: "Storage + Observability",
    subtitle: "Postgres · Langfuse",
    components: [
      { label: "users + sessions", sub: "Alembic" },
      { label: "OAuth accounts", sub: "Google/GitHub" },
      { label: "Langfuse traces", sub: "every run" },
    ],
    highlight: "Run persisted, trace shipped to Langfuse",
    color: "from-amber-500/10 to-amber-500/5",
  },
];

function LayeredStack({
  revealed,
  traceActive,
}: {
  revealed: boolean;
  traceActive: boolean;
}) {
  return (
    <div className="relative">
      {/* Vertical connecting rail behind the layers */}
      <div
        className="absolute left-1/2 top-8 bottom-8 w-px -translate-x-1/2 pointer-events-none"
        style={{
          background:
            "linear-gradient(to bottom, transparent, var(--accent) 10%, var(--accent) 90%, transparent)",
          opacity: revealed ? 0.25 : 0,
          transition: "opacity 1s ease-out",
        }}
      />

      {/* The animated request-trace dot - travels down then back up the rail */}
      {traceActive && (
        <>
          <div
            className="absolute left-1/2 -translate-x-1/2 w-3 h-3 rounded-full pointer-events-none z-20"
            style={{
              top: 0,
              background: "var(--accent-bright)",
              boxShadow: "0 0 12px var(--accent-bright), 0 0 24px var(--accent)",
              animation: "trace-down 7s ease-in-out infinite",
            }}
            aria-hidden
          />
          <style
            dangerouslySetInnerHTML={{
              __html: `
              @keyframes trace-down {
                0%   { top: 2%;   opacity: 0; transform: translate(-50%, 0) scale(0.6); }
                8%   { opacity: 1; transform: translate(-50%, 0) scale(1); }
                45%  { top: 92%;  opacity: 1; transform: translate(-50%, 0) scale(1); }
                52%  { top: 92%;  opacity: 1; transform: translate(-50%, 0) scale(1.4); }
                92%  { top: 2%;   opacity: 1; transform: translate(-50%, 0) scale(1); }
                100% { top: 2%;   opacity: 0; transform: translate(-50%, 0) scale(0.6); }
              }
            `,
            }}
          />
        </>
      )}

      <div className="space-y-3 relative z-10">
        {ARCH_LAYERS.map((layer, idx) => (
          <LayerSlab key={layer.key} layer={layer} index={idx} revealed={revealed} />
        ))}
      </div>
    </div>
  );
}

function LayerSlab({
  layer,
  index,
  revealed,
}: {
  layer: ArchLayer;
  index: number;
  revealed: boolean;
}) {
  return (
    <div
      className="relative rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-base)] overflow-hidden"
      style={{
        opacity: revealed ? 1 : 0,
        transform: revealed ? "translateY(0)" : "translateY(20px)",
        transition: `opacity 0.6s ease-out ${index * 140}ms, transform 0.6s ease-out ${index * 140}ms`,
      }}
    >
      <div
        className="absolute inset-0 pointer-events-none opacity-50"
        style={{
          background: `linear-gradient(135deg, ${getLayerColor(layer.key, 0.12)}, ${getLayerColor(layer.key, 0.03)})`,
        }}
      />

      <div className="relative grid md:grid-cols-[200px_1fr_240px] gap-4 p-4 md:p-5 items-center">
        {/* Left: layer name */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div
              className="w-2 h-2 rounded-full"
              style={{ background: getLayerColor(layer.key, 1) }}
            />
            <div className="text-sm font-semibold text-[var(--fg-primary)]">
              {layer.title}
            </div>
          </div>
          <div className="text-[0.7rem] font-mono text-[var(--fg-tertiary)] pl-4">
            {layer.subtitle}
          </div>
        </div>

        {/* Center: components inside the layer */}
        <div className="flex flex-wrap gap-2">
          {layer.components.map((c) => (
            <div
              key={c.label}
              className="flex flex-col px-3 py-2 rounded-lg bg-[var(--bg-card)] border border-[var(--border-subtle)] min-w-[110px]"
            >
              <span className="text-xs font-medium text-[var(--fg-primary)]">
                {c.label}
              </span>
              <span className="text-[0.6rem] font-mono text-[var(--fg-tertiary)] mt-0.5">
                {c.sub}
              </span>
            </div>
          ))}
        </div>

        {/* Right: what happens at this layer */}
        <div className="hidden md:block text-right">
          <div className="text-[0.7rem] font-mono uppercase tracking-wider text-[var(--accent)] mb-1">
            At this layer
          </div>
          <div className="text-xs text-[var(--fg-secondary)] leading-relaxed">
            {layer.highlight}
          </div>
        </div>
      </div>
    </div>
  );
}

function getLayerColor(key: string, alpha: number): string {
  const colors: Record<string, string> = {
    client: `rgba(34, 211, 238, ${alpha})`,
    edge: `rgba(59, 130, 246, ${alpha})`,
    agent: `rgba(139, 92, 246, ${alpha})`,
    retrieval: `rgba(16, 185, 129, ${alpha})`,
    storage: `rgba(245, 158, 11, ${alpha})`,
  };
  return colors[key] || `rgba(100, 100, 100, ${alpha})`;
}

function ArchInsight({
  num,
  title,
  body,
}: {
  num: string;
  title: string;
  body: string;
}) {
  return (
    <div className="flex gap-3 p-4 rounded-lg bg-[var(--bg-base)] border border-[var(--border-subtle)]">
      <div
        className="shrink-0 text-2xl font-bold bg-clip-text text-transparent leading-none"
        style={{ backgroundImage: "linear-gradient(135deg, var(--accent-bright), var(--accent))" }}
      >
        {num}
      </div>
      <div>
        <div className="font-semibold text-[var(--fg-primary)] text-sm mb-1">
          {title}
        </div>
        <div className="text-xs text-[var(--fg-secondary)] leading-relaxed">
          {body}
        </div>
      </div>
    </div>
  );
}

/* ============================================================================
   Built for Teams — admin panel mock with polished rows
   ========================================================================== */
function BuiltForTeams() {
  return (
    <section className="py-20 md:py-28 border-t border-[var(--border-subtle)]">
      <div className="max-w-6xl mx-auto px-6">
        <div className="grid md:grid-cols-2 gap-12 items-center">
          <div className="order-2 md:order-1 relative reveal-init">
            <div
              className="absolute inset-0 rounded-2xl opacity-20 blur-2xl pointer-events-none"
              style={{ background: "linear-gradient(135deg, var(--accent-bright), var(--accent))" }}
            />
            <div className="relative bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-xl overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--border-subtle)] bg-[var(--bg-sidebar)]">
                <ShieldCheck className="w-3.5 h-3.5 text-[var(--accent)]" />
                <span className="text-[0.7rem] font-mono text-[var(--fg-tertiary)]">Admin / Users</span>
                <span className="ml-auto text-[0.6rem] font-mono text-[var(--fg-tertiary)]">4 users</span>
              </div>
              <div className="p-4 text-sm space-y-2">
                <AdminRow email="alice@acme.com" name="Alice Chen" role="super_admin" status="active" />
                <AdminRow email="bob@acme.com" name="Bob Martinez" role="corpus_admin" status="active" />
                <AdminRow email="charlie@acme.com" name="Charlie Park" role="user" status="active" />
                <AdminRow email="ex.contractor@acme.com" name="J. Williams" role="user" status="suspended" />
                <div className="pt-3 border-t border-[var(--border-subtle)] flex flex-wrap gap-2 text-[0.65rem] font-mono">
                  <ActionPill icon={<Lock className="w-3 h-3" />} label="suspend + email" />
                  <ActionPill icon={<ArrowRight className="w-3 h-3" />} label="force-logout" />
                  <ActionPill icon={<Sparkles className="w-3 h-3" />} label="send reset" />
                </div>
              </div>
            </div>
          </div>

          <div className="order-1 md:order-2 reveal-init">
            <div className="text-xs font-mono uppercase tracking-wider text-[var(--accent)] mb-3">Built for teams</div>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">Real user management, not a settings page.</h2>
            <p className="text-[var(--fg-secondary)] leading-relaxed mb-6">
              CloudNest ships with the admin tooling most internal AI projects never bother to build.
              Onboard users, define roles, curate what the AI knows about your company, and shut down a
              compromised account before someone gets a chance to misuse it.
            </p>
            <ul className="space-y-3 text-sm text-[var(--fg-secondary)]">
              <FeatureLine icon={Users} title="Three-tier roles" body="Regular users, corpus admins who manage the knowledge base, and super admins who manage everything." />
              <FeatureLine icon={ShieldCheck} title="Suspend with one click" body="Block an account, force-logout active sessions instantly, and email the user with a clear reason. Unblock is just as fast." />
              <FeatureLine icon={Search} title="Curate the knowledge base" body="Drag in PDFs and manuals. Preview retrieval with hybrid search before users see it. Delete sources cleanly." />
              <FeatureLine icon={LineChart} title="Observe everything" body="Every agent run is traced. Inspect tool calls, latencies, token usage. Debug bad answers with full reproducibility." />
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function FeatureLine({
  icon: Icon,
  title,
  body,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
}) {
  return (
    <li className="flex items-start gap-3">
      <Icon className="w-4 h-4 text-[var(--accent)] mt-0.5 shrink-0" />
      <span>
        <span className="font-medium text-[var(--fg-primary)]">{title}.</span> {body}
      </span>
    </li>
  );
}

function ActionPill({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-[var(--bg-base)] border border-[var(--border-subtle)] text-[var(--fg-tertiary)]">
      {icon}
      {label}
    </span>
  );
}

function AdminRow({
  email,
  name,
  role,
  status,
}: {
  email: string;
  name: string;
  role: string;
  status: "active" | "suspended";
}) {
  const initials = name
    .split(" ")
    .map((n) => n[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <div className="flex items-center justify-between gap-3 p-2 rounded-lg hover:bg-[var(--bg-base)]/50 transition-colors">
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-semibold text-white shrink-0"
          style={{ background: "linear-gradient(135deg, var(--accent-bright), var(--accent))" }}
        >
          {initials}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-[var(--fg-primary)] truncate">{name}</div>
          <div className="text-[0.65rem] text-[var(--fg-tertiary)] truncate font-mono">{email}</div>
        </div>
      </div>
      <span className="text-[0.65rem] font-mono px-2 py-0.5 rounded bg-[var(--bg-base)] border border-[var(--border-subtle)] text-[var(--fg-secondary)] shrink-0">
        {role}
      </span>
      <span
        className={`text-[0.65rem] font-mono px-2 py-0.5 rounded shrink-0 flex items-center gap-1.5 ${
          status === "active"
            ? "text-emerald-500 bg-emerald-500/10 border border-emerald-500/30"
            : "text-red-500 bg-red-500/10 border border-red-500/30"
        }`}
      >
        {status === "active" && <span className="block w-1 h-1 rounded-full bg-emerald-500 pulse-soft" />}
        {status}
      </span>
    </div>
  );
}

/* ============================================================================
   Use cases (kept content, slightly tighter visual treatment)
   ========================================================================== */
const USE_CASES = [
  { icon: Building2, title: "Internal company AI", body: "Give every employee an AI assistant that already knows your company's policies, SOPs, product documentation, and pricing. Each person also gets a private space for their own working documents.", tags: ["Operations", "HR", "Sales"] },
  { icon: HeartPulse, title: "Regulated industries", body: "Healthcare, legal, finance - any vertical where data cannot leave your perimeter. Self-host on your own VPC. Use Ollama for fully local inference. CloudNest does not phone home.", tags: ["HIPAA-aware", "On-prem", "Air-gapped"] },
  { icon: GraduationCap, title: "Universities & research", body: "Each student or researcher gets their own RAG corpus. Faculty curates a shared knowledge base of textbooks and syllabi. 37 native voices including Urdu, Arabic, Bengali, Hindi.", tags: ["EdTech", "Multilingual"] },
  { icon: Gavel, title: "Law firms & consultancies", body: "Upload case files, contracts, and prior memos to a partner's private workspace. Cite the exact filename and page. Use ensemble mode to compare how different models interpret an ambiguous clause.", tags: ["Citation-grade", "Confidential"] },
  { icon: Boxes, title: "Customer support copilot", body: "Load product manuals and troubleshooting guides into the shared knowledge base. Every support agent gets fast, citation-backed answers without sending customer data to a third-party AI.", tags: ["CX", "Internal"] },
  { icon: GraduationCap, title: "Training & onboarding", body: "Drop your onboarding handbook, role-specific playbooks, and historical training material into the knowledge base. New hires ask questions and get grounded answers with verifiable sources.", tags: ["L&D", "Knowledge mgmt"] },
];

function UseCases() {
  return (
    <section id="use-cases" className="py-20 md:py-28 border-t border-[var(--border-subtle)]">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-14 reveal-init">
          <div className="text-xs font-mono uppercase tracking-wider text-[var(--accent)] mb-3">Where teams use it</div>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight">One platform. Many shapes.</h2>
          <p className="text-[var(--fg-secondary)] mt-3 max-w-xl mx-auto">
            The same architecture - per-user isolation, shared knowledge base, switchable LLM providers -
            fits a wide range of organizational needs.
          </p>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {USE_CASES.map((u, i) => (
            <UseCaseCard key={u.title} {...u} delay={i * 40} />
          ))}
        </div>
      </div>
    </section>
  );
}

function UseCaseCard({
  icon: Icon,
  title,
  body,
  tags,
  delay,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
  tags: string[];
  delay: number;
}) {
  return (
    <div
      className="reveal-init group relative p-6 rounded-xl bg-[var(--bg-card)] border border-[var(--border-subtle)] hover:border-[var(--accent)]/40 hover:-translate-y-1 transition-all duration-300 flex flex-col"
      style={{ transitionDelay: `${delay}ms` }}
    >
      <div className="w-10 h-10 rounded-lg flex items-center justify-center mb-4 bg-[var(--accent-soft)] border border-[var(--border-subtle)]">
        <Icon className="w-5 h-5 text-[var(--accent)]" />
      </div>
      <h3 className="text-base font-semibold text-[var(--fg-primary)] mb-2">{title}</h3>
      <p className="text-sm text-[var(--fg-secondary)] leading-relaxed flex-1">{body}</p>
      <div className="mt-4 flex flex-wrap gap-1.5">
        {tags.map((t) => (
          <span
            key={t}
            className="text-[0.65rem] font-mono px-2 py-0.5 rounded bg-[var(--bg-base)] border border-[var(--border-subtle)] text-[var(--fg-tertiary)]"
          >
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ============================================================================
   Provider switch demo - unchanged content, slight presentation polish
   ========================================================================== */
function ProviderSwitchDemo() {
  return (
    <section className="py-20 md:py-28 border-t border-[var(--border-subtle)]">
      <div className="max-w-6xl mx-auto px-6">
        <div className="grid md:grid-cols-2 gap-12 items-center">
          <div className="reveal-init">
            <div className="text-xs font-mono uppercase tracking-wider text-[var(--accent)] mb-3">No vendor lock-in</div>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">Switch LLMs in one line.</h2>
            <p className="text-[var(--fg-secondary)] leading-relaxed mb-6">
              CloudNest is built against a provider abstraction. Run on Groq for raw speed, OpenRouter
              for access to Claude/GPT-4/Gemini through one key, or Ollama for fully local inference.
              When a new provider ships, it&apos;s one branch in the LLM factory.
            </p>
            <ul className="space-y-2 text-sm text-[var(--fg-secondary)]">
              <li className="flex items-start gap-2">
                <span className="text-[var(--accent)] mt-1">&rarr;</span>
                <span><span className="font-medium text-[var(--fg-primary)]">Groq</span> - sub-second responses on Llama and gpt-oss models</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-[var(--accent)] mt-1">&rarr;</span>
                <span><span className="font-medium text-[var(--fg-primary)]">OpenRouter</span> - access to ~100 models including Claude, GPT-4o, Gemini, DeepSeek</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-[var(--accent)] mt-1">&rarr;</span>
                <span><span className="font-medium text-[var(--fg-primary)]">Ollama</span> - fully local inference for privacy-sensitive deployments</span>
              </li>
            </ul>
          </div>

          <div className="relative reveal-init">
            <div
              className="absolute inset-0 rounded-2xl opacity-20 blur-2xl pointer-events-none"
              style={{ background: "linear-gradient(135deg, var(--accent-bright), var(--accent))" }}
            />
            <div className="relative bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-xl overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[var(--border-subtle)] bg-[var(--bg-sidebar)]">
                <FileText className="w-3.5 h-3.5 text-[var(--fg-tertiary)]" />
                <span className="text-[0.7rem] font-mono text-[var(--fg-tertiary)]">.env</span>
              </div>
              <pre className="p-5 text-xs font-mono leading-relaxed text-[var(--fg-secondary)] overflow-x-auto">
                <code>
                  <span className="text-[var(--fg-muted)]"># Switch the entire platform with one line:</span>
                  {"\n\n"}
                  <span className="text-[var(--accent)]">LLM_PROVIDER</span>=groq
                  {"\n"}
                  <span className="text-[var(--fg-muted)]"># or</span>
                  {"\n"}
                  <span className="text-[var(--accent)]">LLM_PROVIDER</span>=openrouter
                  {"\n"}
                  <span className="text-[var(--fg-muted)]"># or</span>
                  {"\n"}
                  <span className="text-[var(--accent)]">LLM_PROVIDER</span>=ollama
                  {"\n\n"}
                  <span className="text-[var(--fg-muted)]"># Restart. Done.</span>
                </code>
              </pre>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ============================================================================
   How it works (3 steps) - unchanged content, reveal animation
   ========================================================================== */
const STEPS = [
  { n: "01", title: "Deploy in minutes", body: "One docker-compose command brings up the full stack: API, Postgres, Weaviate, frontend. Run it on your laptop, your VPC, or bare metal." },
  { n: "02", title: "Onboard your team", body: "Invite users. Assign roles. Curate the shared knowledge base. Every user also gets their own private document space." },
  { n: "03", title: "Ask anything", body: "Your team starts using AI immediately. The agent reads your docs, calls tools, searches the web, and answers with sources - across 100+ languages." },
];

function HowItWorks() {
  return (
    <section className="py-20 md:py-28 border-t border-[var(--border-subtle)] bg-[var(--bg-sidebar)]/30">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-14 reveal-init">
          <div className="text-xs font-mono uppercase tracking-wider text-[var(--accent)] mb-3">How it works</div>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight">From zero to your own AI in three steps.</h2>
        </div>
        <div className="grid md:grid-cols-3 gap-6">
          {STEPS.map((s, i) => (
            <div
              key={s.n}
              className="reveal-init relative p-6 rounded-xl bg-[var(--bg-card)] border border-[var(--border-subtle)] h-full hover:border-[var(--accent)]/30 transition"
              style={{ transitionDelay: `${i * 80}ms` }}
            >
              <div
                className="text-3xl font-bold bg-clip-text text-transparent mb-3"
                style={{ backgroundImage: "linear-gradient(135deg, var(--accent-bright), var(--accent))" }}
              >
                {s.n}
              </div>
              <h3 className="text-lg font-semibold mb-2">{s.title}</h3>
              <p className="text-sm text-[var(--fg-secondary)] leading-relaxed">{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ============================================================================
   Tech stack - same data, with reveal animation
   ========================================================================== */
const STACK = [
  { icon: Network, label: "FastAPI + LangGraph", desc: "async Python backend with ReAct agent loops" },
  { icon: Database, label: "Postgres + Weaviate", desc: "users, sessions, multi-tenant vector stores" },
  { icon: Globe, label: "BAAI/bge-m3 embeddings", desc: "1024-dim multilingual vectors, 100+ languages" },
  { icon: Cloud, label: "Groq / OpenRouter / Ollama", desc: "3 LLM providers, switchable in one line" },
  { icon: Eye, label: "Vision + voice", desc: "Llama-4 Scout, Whisper STT, Edge TTS" },
  { icon: LineChart, label: "Langfuse tracing", desc: "every agent run captured with full tool tree" },
  { icon: Container, label: "Docker-native", desc: "single docker-compose for the full stack" },
  { icon: Lock, label: "fastapi-users + Alembic", desc: "JWT + cookies, OAuth, migrations" },
];

const UNDER_THE_HOOD = [
  "httpOnly cookie auth + Bearer JWT (dual transport)",
  "Streaming responses via SSE with live tool traces",
  "Per-user Weaviate tenants enforced at the storage layer",
  "Global force-logout via JWT iat-cutoff checks",
  "Account suspension with email notifications + reason",
  "Hybrid retrieval (BM25 + vector) merged across corpora",
  "Cross-lingual semantic search via BGE-M3",
  "Auto-generated chat titles via background worker",
];

function TechStack() {
  return (
    <section id="stack" className="py-20 md:py-28 border-t border-[var(--border-subtle)]">
      <div className="max-w-6xl mx-auto px-6">
        <div className="text-center mb-14 reveal-init">
          <div className="text-xs font-mono uppercase tracking-wider text-[var(--accent)] mb-3">Built on</div>
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight">Honest engineering choices.</h2>
          <p className="text-[var(--fg-secondary)] mt-3 max-w-xl mx-auto">
            No black boxes. Well-understood components wired carefully and tested end-to-end.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {STACK.map((s, i) => {
            const Icon = s.icon;
            return (
              <div
                key={s.label}
                className="reveal-init p-5 rounded-xl bg-[var(--bg-card)] border border-[var(--border-subtle)] hover:border-[var(--accent)]/30 hover:-translate-y-0.5 transition-all duration-300"
                style={{ transitionDelay: `${i * 30}ms` }}
              >
                <Icon className="w-5 h-5 text-[var(--accent)] mb-3" />
                <div className="text-sm font-semibold text-[var(--fg-primary)] mb-1">{s.label}</div>
                <div className="text-xs text-[var(--fg-tertiary)] leading-relaxed">{s.desc}</div>
              </div>
            );
          })}
        </div>

        <div className="mt-10 p-6 rounded-xl bg-[var(--bg-card)] border border-[var(--border-subtle)] reveal-init">
          <div className="text-xs font-mono uppercase tracking-wider text-[var(--fg-tertiary)] mb-3">Under the hood</div>
          <ul className="grid md:grid-cols-2 gap-x-8 gap-y-2 text-sm text-[var(--fg-secondary)]">
            {UNDER_THE_HOOD.map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span className="text-[var(--accent)] mt-1">&rarr;</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

/* ============================================================================
   Final CTA - sharpened, with a subtle 'dots' field
   ========================================================================== */
function FinalCTA() {
  return (
    <section className="relative py-24 md:py-32 border-t border-[var(--border-subtle)] overflow-hidden">
      <div
        className="absolute inset-0 opacity-15 pointer-events-none"
        style={{ background: "radial-gradient(circle at 50% 50%, var(--accent-bright) 0%, transparent 55%)" }}
      />
      <div
        className="absolute inset-0 opacity-[0.04] pointer-events-none"
        style={{
          backgroundImage: "radial-gradient(var(--fg-primary) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />
      <div className="relative max-w-3xl mx-auto px-6 text-center reveal-init">
        <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-5 leading-tight">
          Your AI.{" "}
          <span className="bg-clip-text text-transparent" style={{ backgroundImage: "linear-gradient(135deg, var(--accent-bright), var(--accent))" }}>
            Your infrastructure.
          </span>{" "}
          Your data.
        </h2>
        <p className="text-base md:text-lg text-[var(--fg-secondary)] mb-10 max-w-md mx-auto">
          Try the hosted demo, or clone the repo and run the full stack on your own machine in minutes.
        </p>
        <div className="flex flex-wrap gap-3 justify-center">
          <Link
            href="/signup"
            className="group inline-flex items-center gap-2 px-7 py-3.5 rounded-md bg-[var(--accent)] hover:bg-[var(--accent-bright)] text-white text-sm font-medium transition-all shadow-lg shadow-[var(--accent)]/20 hover:shadow-xl hover:shadow-[var(--accent)]/30 hover:-translate-y-0.5"
          >
            Try the demo
            <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
          </Link>
          <a
            href="https://github.com/Muhammad-Munir-Khan/cloudnest-ai"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-7 py-3.5 rounded-md border border-[var(--border-subtle)] hover:border-[var(--accent)]/40 text-[var(--fg-primary)] text-sm font-medium transition"
          >
            <Github className="w-4 h-4" />
            View on GitHub
          </a>
        </div>
      </div>
    </section>
  );
}

/* ============================================================================
   Footer
   ========================================================================== */
function SiteFooter() {
  return (
    <footer className="border-t border-[var(--border-subtle)] py-10">
      <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-[var(--fg-tertiary)]">
        <Wordmark size="sm" />
        <div className="flex flex-wrap items-center justify-center gap-4">
          <span className="font-mono">
            Built by{" "}
            <a
              href="https://www.linkedin.com/in/munirkhan-ai/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--fg-secondary)] hover:text-[var(--accent)] transition font-semibold"
            >
              Muhammad Munir Khan
            </a>
          </span>
          <span className="text-[var(--border-subtle)]">|</span>
          <a
            href="https://github.com/Muhammad-Munir-Khan"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 hover:text-[var(--fg-primary)] transition"
          >
            <Github className="w-3.5 h-3.5" />
            GitHub
          </a>
          <span className="text-[var(--border-subtle)]">|</span>
          <span className="font-mono">FastAPI / Next.js / Postgres / Weaviate / Docker</span>
        </div>
      </div>
    </footer>
  );
}