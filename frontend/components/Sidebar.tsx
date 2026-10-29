"use client";

import {
  Bot,
  ChevronRight,
  Cloud,
  FileText,
  Languages,
  Palette,
  Shield,
  Sparkles,
} from "lucide-react";
import Link from "next/link";

import type { Mode } from "@/lib/types";
import type { SessionInfo } from "@/lib/api";
import type { Theme } from "@/lib/theme";
import type { LanguageCode } from "@/lib/language";
import { cn } from "@/lib/utils";

import { useAuth } from "@/components/AuthProvider";
import { ChatList } from "./ChatList";
import { ThemeToggle } from "./ThemeToggle";
import { LanguageSelector } from "./LanguageSelector";
import { DocumentManager } from "./DocumentManager";
import { UserFooter } from "./UserFooter";

const ADMIN_ROLES = ["corpus_admin", "super_admin"];

export function Sidebar({
  mode,
  setMode,
  ensembleEnabled,
  setEnsembleEnabled,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onRenameSession,
  onDeleteSession,
  theme,
  onToggleTheme,
  language,
  setLanguage,
}: {
  mode: Mode;
  setMode: (m: Mode) => void;
  ensembleEnabled: boolean;
  setEnsembleEnabled: (v: boolean) => void;
  sessions: SessionInfo[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onRenameSession: (id: string, title: string) => void;
  onDeleteSession: (id: string) => void;
  theme: Theme;
  onToggleTheme: () => void;
  language: LanguageCode;
  setLanguage: (code: LanguageCode) => void;
}) {
  const { user } = useAuth();
  const role = (user as { role?: string } | null)?.role ?? "user";
  const isAdmin = ADMIN_ROLES.includes(role);

  return (
    <aside className="w-[280px] shrink-0 border-r border-[var(--border-subtle)] bg-[var(--bg-sidebar)] px-5 py-6 sticky top-0 h-screen overflow-y-auto flex flex-col">
      {/* ---------- Wordmark ---------- */}
      <Link
        href="/"
        aria-label="CloudNest home"
        className="inline-flex items-baseline gap-1.5 mb-6 group w-fit"
      >
        <Cloud
          className="w-[18px] h-[18px] text-[var(--accent)] self-center transition-transform group-hover:scale-110"
          strokeWidth={2.25}
        />
        <span
          className="text-lg font-bold bg-clip-text text-transparent tracking-tight"
          style={{
            backgroundImage:
              "linear-gradient(135deg, var(--accent-bright), var(--accent))",
          }}
        >
          CloudNest
        </span>
        <span className="text-xs font-mono text-[var(--fg-tertiary)] opacity-70 -ml-1">
          .ai
        </span>
      </Link>

      {/* ---------- Admin entry point (admins only) ----------
       * Robust premium-feel admin button:
       *   - explicit RGB colors so it can't blend with sidebar background
       *   - clear color separation (deep indigo/purple gradient -> white text)
       *   - "ADMIN ACCESS" microcopy + "Switch to panel" action
       *   - shield badge with subtle ring
       *   - chevron arrow nudges right on hover
       *   - 2px lift + shadow growth on hover
       */}
      {isAdmin && (
        <Link
          href="/admin"
          className="group relative mb-6 flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg text-white transition-all duration-200 shadow-md hover:shadow-lg hover:-translate-y-0.5"
          style={{
            background:
              "linear-gradient(135deg, var(--accent-bright) 0%, var(--accent) 100%)",
            boxShadow:
              "0 4px 14px var(--accent-glow), inset 0 1px 0 rgba(255, 255, 255, 0.18)",
          }}
        >
          <span
            className="shrink-0 w-7 h-7 rounded-md flex items-center justify-center"
            style={{
              background: "rgba(255, 255, 255, 0.15)",
              border: "1px solid rgba(255, 255, 255, 0.25)",
            }}
          >
            <Shield className="w-3.5 h-3.5 text-white" strokeWidth={2.5} />
          </span>
          <span className="flex-1 min-w-0 flex flex-col">
            <span
              className="text-[0.6rem] font-mono tracking-[0.16em] uppercase leading-none mb-1"
              style={{ color: "rgba(255, 255, 255, 0.75)" }}
            >
              Admin Access
            </span>
            <span className="text-xs font-semibold text-white leading-none">
              Switch to panel
            </span>
          </span>
          <ChevronRight
            className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5"
            style={{ color: "rgba(255, 255, 255, 0.75)" }}
          />
        </Link>
      )}

      {/* ---------- Appearance ---------- */}
      <SectionHeader icon={Palette} first>Appearance</SectionHeader>
      <ThemeToggle theme={theme} onToggle={onToggleTheme} />

      {/* ---------- Language ---------- */}
      <SectionHeader icon={Languages}>Language</SectionHeader>
      <LanguageSelector value={language} onChange={setLanguage} />

      {/* ---------- Chats ---------- */}
      <SectionHeader icon={Bot}>Chats</SectionHeader>
      <ChatList
        sessions={sessions}
        activeId={activeSessionId}
        onSelect={onSelectSession}
        onNew={onNewChat}
        onRename={onRenameSession}
        onDelete={onDeleteSession}
      />

      {/* ---------- Response mode (combined: Agent / RAG / Multi-LLM) ---------- */}
      <SectionHeader icon={Sparkles}>Response mode</SectionHeader>
      <div className="flex flex-col gap-1.5">
        <ModeOption
          label="Agent"
          desc="Multi-step, can use tools"
          selected={!ensembleEnabled && mode === "agent"}
          disabled={ensembleEnabled}
          onClick={() => setMode("agent")}
        />
        <ModeOption
          label="RAG only"
          desc="Single-shot doc Q&A"
          selected={!ensembleEnabled && mode === "rag"}
          disabled={ensembleEnabled}
          onClick={() => setMode("rag")}
        />
        <ModeOption
          label="Multi-LLM ensemble"
          desc="3 Groq models in parallel, judged by Llama 70B"
          selected={ensembleEnabled}
          onClick={() => setEnsembleEnabled(!ensembleEnabled)}
          accentIcon
        />
      </div>
      {ensembleEnabled && (
        <div className="mt-2 px-3 py-1.5 rounded-md bg-[var(--accent-soft)] text-[0.65rem] text-[var(--fg-secondary)] font-mono leading-snug">
          Bypasses agent + RAG. No tools, no memory.
        </div>
      )}

      {/* ---------- Documents ---------- */}
      <SectionHeader icon={FileText}>Documents</SectionHeader>
      <DocumentManager />

      {/* spacer pushes the user footer to the bottom */}
      <div className="flex-1 min-h-[1.5rem]" />

      <UserFooter activeSessionId={activeSessionId} variant="chat" />
    </aside>
  );
}

/* ============================================================================
   Section header - now with an optional left icon. Adds a subtle hairline
   above each section so the sidebar visually groups by topic instead of
   running as one continuous stream of labels.
   ========================================================================== */

function SectionHeader({
  icon: Icon,
  children,
  first,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
  first?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-1.5",
        first
          ? "mt-0 mb-2.5"
          : "mt-6 mb-2.5 pt-3 border-t border-[var(--border-subtle)]",
      )}
    >
      {Icon && <Icon className="w-3 h-3 text-[var(--accent)]/70" />}
      <span className="font-mono text-[0.7rem] tracking-[0.14em] uppercase text-[var(--fg-tertiary)]">
        {children}
      </span>
    </div>
  );
}

/* ============================================================================
   Mode option - now uses accent CSS variables instead of hardcoded cyan-*
   so it tracks your theme accent correctly in both light and dark.
   ========================================================================== */

function ModeOption({
  label,
  desc,
  selected,
  disabled,
  onClick,
  accentIcon,
}: {
  label: string;
  desc: string;
  selected: boolean;
  disabled?: boolean;
  onClick: () => void;
  accentIcon?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "group text-left px-3 py-2 rounded-md border transition-all",
        disabled && "opacity-40 cursor-not-allowed",
        !disabled && selected
          ? "bg-[var(--accent-soft)] border-[var(--accent)]/40 shadow-sm"
          : "bg-[var(--bg-card)] border-[var(--border-subtle)] hover:border-[var(--accent)]/30 hover:bg-[var(--accent-soft)]/40",
      )}
    >
      <div className="flex items-center gap-1.5">
        {accentIcon && (
          <Sparkles
            className={cn(
              "w-3 h-3 transition-colors",
              selected ? "text-[var(--accent)]" : "text-[var(--fg-tertiary)]",
            )}
          />
        )}
        <span
          className={cn(
            "text-xs font-semibold",
            selected && !disabled
              ? "text-[var(--accent)]"
              : "text-[var(--fg-primary)]",
          )}
        >
          {label}
        </span>
        {selected && !disabled && (
          <span className="ml-auto block w-1.5 h-1.5 rounded-full bg-[var(--accent)] shadow-[0_0_6px_var(--accent-glow)]" />
        )}
      </div>
      <div
        className={cn(
          "text-[0.68rem] mt-0.5 leading-snug",
          selected && !disabled
            ? "text-[var(--fg-secondary)]"
            : "text-[var(--fg-tertiary)]",
        )}
      >
        {desc}
      </div>
    </button>
  );
}