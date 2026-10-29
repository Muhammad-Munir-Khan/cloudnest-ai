"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  agentChat,
  deleteSession,
  ensembleChat,
  extractAttachment,
  getSessionMessages,
  listSessions,
  ragQuery,
  renameSession,
  streamAgent,
  transcribe,
  type SessionInfo,
} from "@/lib/api";
import type {
  ChatMessage,
  Mode,
  TraceEntry,
} from "@/lib/types";
import { useTheme } from "@/lib/theme";
import { useLanguage } from "@/lib/language";
import { uuid } from "@/lib/utils";

import { useAuth } from "@/components/AuthProvider";
import { Hero } from "@/components/Hero";
import { Sidebar } from "@/components/Sidebar";
import { EmptyState } from "@/components/EmptyState";
import { Composer, type PendingAttachment } from "@/components/Composer";
import { ChatMessageView } from "@/components/ChatMessage";

export default function Home() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();

  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [sessionId, setSessionId] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const [mode, setMode] = useState<Mode>("agent");
  const [ensembleEnabled, setEnsembleEnabled] = useState(false);

  const [pendingAttachment, setPendingAttachment] =
    useState<PendingAttachment | null>(null);
  const [attaching, setAttaching] = useState(false);

  const [busy, setBusy] = useState(false);
  const [prefill, setPrefill] = useState<string | undefined>();

  const [liveTrace, setLiveTrace] = useState<TraceEntry[]>([]);
  const [liveAnswer, setLiveAnswer] = useState<string>("");
  const [liveMessageId, setLiveMessageId] = useState<string | null>(null);

  const { theme, toggle: toggleTheme } = useTheme();
  const { language, setLanguage } = useLanguage();

  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);
  // Always holds the currently-active session id. Async handlers (e.g.
  // transcription) capture the session at call time and compare against this
  // ref when they resolve, so a result from an abandoned session is dropped
  // rather than leaking into whatever chat is now active.
  const sessionIdRef = useRef<string>("");

  /* --------------- Auth gating: kick out anon users to /login ----------- */
  useEffect(() => {
    if (!authLoading && !user) {
      router.replace("/login");
    }
  }, [authLoading, user, router]);

  // Keep sessionIdRef in sync with the sessionId state.
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await listSessions());
    } catch (e) {
      console.warn("Failed to load sessions:", e);
    }
  }, []);

  useEffect(() => {
    if (!sessionId) setSessionId(uuid());
  }, [sessionId]);

  useEffect(() => {
    // Only fetch sessions once we know the user is authenticated;
    // otherwise we'd race the redirect with a flurry of 401-and-redirect cycles.
    if (!user) return;
    refreshSessions();
  }, [user, refreshSessions]);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [messages, liveTrace, liveAnswer]);

  /* ------------------------------ Session switching ----------------------- */

  const handleSelectSession = async (id: string) => {
    if (id === sessionId || busy) return;
    setBusy(true);
    try {
      const stored = await getSessionMessages(id);
      const replayed: ChatMessage[] = stored.map((m) => ({
        id: `${m.id}`,
        role: m.role === "user" ? "user" : "assistant",
        content: m.content,
      }));
      setMessages(replayed);
      setSessionId(id);
      setPendingAttachment(null);
      setPrefill(undefined);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to load chat");
    } finally {
      setBusy(false);
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setSessionId(uuid());
    setPendingAttachment(null);
    setPrefill(undefined);
  };

  const handleRenameSession = async (id: string, title: string) => {
    try {
      await renameSession(id, title);
      await refreshSessions();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Rename failed");
    }
  };

  const handleDeleteSession = async (id: string) => {
    try {
      await deleteSession(id);
      if (id === sessionId) handleNewChat();
      await refreshSessions();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Delete failed");
    }
  };

  /* ------------------------------ Attachments ----------------------------- */

  const handleAttachFile = async (file: File) => {
    setAttaching(true);
    try {
      const result = await extractAttachment(file, false);
      setPendingAttachment({
        name: result.filename,
        text: result.text,
        method: result.method,
        bytes: result.size_bytes,
      });
    } catch (e) {
      alert(e instanceof Error ? e.message : "Attachment failed");
    } finally {
      setAttaching(false);
    }
  };

  /* ------------------------------ Voice (STT only) ------------------------ */
  /* TTS is now per-message via <TTSButton> inside ChatMessageView. The
   * sidebar global "speak responses" toggle has been removed. */

  const handleTranscribe = async (blob: Blob) => {
    // Capture the session that was active when recording finished. If the user
    // switches chats or starts a new one while transcription is in flight, the
    // resolved transcript belongs to a session that's no longer active and is
    // discarded instead of leaking into the current composer.
    const startedSession = sessionIdRef.current;
    try {
      const result = await transcribe(blob);
      if (sessionIdRef.current !== startedSession) return;
      if (result.text?.trim()) setPrefill(result.text);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Transcription failed");
    }
  };

  /* ------------------------------ Submit ---------------------------------- */

  const handleSubmit = async (text: string) => {
    if (busy || !sessionId) return;
    const attached = pendingAttachment;
    setPendingAttachment(null);
    setPrefill(undefined);

    const wasEmpty = messages.length === 0;

    const userMessage: ChatMessage = {
      id: uuid(),
      role: "user",
      content: text,
      attachmentName: attached?.name,
    };
    const assistantId = uuid();

    setMessages((prev) => [...prev, userMessage]);
    setLiveTrace([]);
    setLiveAnswer("");
    setLiveMessageId(assistantId);
    setBusy(true);

    try {
      // ---------- Multi-LLM ensemble (bypasses agent + RAG entirely) -----
      if (ensembleEnabled) {
        const data = await ensembleChat(text, language);
        const assistantMsg: ChatMessage = {
          id: assistantId,
          role: "assistant",
          content: data.verdict,
          ensemble: data,
          latencyMs: data.total_latency_ms,
        };
        setMessages((prev) => [...prev, assistantMsg]);
        await refreshSessions();
        return;
      }

      // ---------- RAG mode ------------------------------------------------
      if (mode === "rag") {
        const data = await ragQuery(text, language);
        const assistantMsg: ChatMessage = {
          id: assistantId,
          role: "assistant",
          content: data.answer,
          sources: data.sources,
          latencyMs: data.latency_ms,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } else {
        // ---------- Agent mode (streaming + fallback) ---------------------
        try {
          const traceList: TraceEntry[] = [];
          let answer = "";
          let final: {
            sources: ChatMessage["sources"];
            toolCalls: ChatMessage["toolCalls"];
            latencyMs: number;
          } = {
            sources: [],
            toolCalls: [],
            latencyMs: 0,
          };

          for await (const evt of streamAgent({
            message: text,
            session_id: sessionId,
            attachment_text: attached?.text,
            attachment_name: attached?.name,
            language,
          })) {
            if (evt.type === "tool_start") {
              traceList.push({
                name: evt.name,
                args: evt.args,
                status: "running",
              });
              setLiveTrace([...traceList]);
            } else if (evt.type === "tool_end") {
              for (let i = traceList.length - 1; i >= 0; i--) {
                if (
                  traceList[i].name === evt.name &&
                  traceList[i].status === "running"
                ) {
                  traceList[i] = {
                    ...traceList[i],
                    status: "done",
                    preview: evt.preview,
                  };
                  break;
                }
              }
              setLiveTrace([...traceList]);
            } else if (evt.type === "token") {
              answer += evt.delta;
              setLiveAnswer(answer);
            } else if (evt.type === "done") {
              answer = evt.answer || answer;
              final = {
                sources: evt.sources,
                toolCalls: evt.tool_calls,
                latencyMs: evt.latency_ms,
              };
            } else if (evt.type === "error") {
              throw new Error(evt.message);
            }
          }

          const assistantMsg: ChatMessage = {
            id: assistantId,
            role: "assistant",
            content: answer,
            sources: final.sources,
            toolCalls: final.toolCalls,
            trace: traceList,
            latencyMs: final.latencyMs,
          };
          setMessages((prev) => [...prev, assistantMsg]);
        } catch (streamErr) {
          console.warn("Stream failed, falling back to /agent/chat:", streamErr);
          const data = await agentChat({
            message: text,
            session_id: sessionId,
            attachment_text: attached?.text,
            attachment_name: attached?.name,
            language,
          });
          const assistantMsg: ChatMessage = {
            id: assistantId,
            role: "assistant",
            content: data.answer,
            sources: data.sources,
            toolCalls: data.tool_calls,
            latencyMs: data.latency_ms,
          };
          setMessages((prev) => [...prev, assistantMsg]);
        }
      }

      await refreshSessions();
      if (wasEmpty) {
        setTimeout(() => {
          void refreshSessions();
        }, 1500);
        setTimeout(() => {
          void refreshSessions();
        }, 4000);
      }
    } catch (e) {
      const errorMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: `⚠ ${e instanceof Error ? e.message : "Request failed"}`,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setBusy(false);
      setLiveTrace([]);
      setLiveAnswer("");
      setLiveMessageId(null);
    }
  };

  const showStreamingPlaceholder =
    busy && liveMessageId !== null && !ensembleEnabled;
  const showEnsembleLoading =
    busy && ensembleEnabled && liveMessageId !== null;

  /* --------------- Loading / unauthenticated states -------------------- */

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg-base)]">
        <div className="text-xs font-mono uppercase tracking-wider text-[var(--fg-tertiary)]">
          loading...
        </div>
      </div>
    );
  }

  if (!user) {
    // useEffect above is already redirecting; render nothing for the split second
    // between detection and navigation completing.
    return null;
  }

  /* ------------------------------ Main UI ------------------------------ */

  return (
    <div className="flex min-h-screen">
      <Sidebar
        mode={mode}
        setMode={setMode}
        ensembleEnabled={ensembleEnabled}
        setEnsembleEnabled={setEnsembleEnabled}
        sessions={sessions}
        activeSessionId={sessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
        theme={theme}
        onToggleTheme={toggleTheme}
        language={language}
        setLanguage={setLanguage}
      />

      <main className="flex-1 flex flex-col px-6 md:px-10 py-8 max-w-[1280px] mx-auto w-full">
        <Hero />

        <div className="flex-1 flex flex-col">
          {messages.length === 0 &&
          !showStreamingPlaceholder &&
          !showEnsembleLoading ? (
            <EmptyState onPick={(t) => setPrefill(t)} />
          ) : (
            <div className="space-y-4 pb-4">
              {messages.map((m) => (
                <div key={m.id} className="fade-in">
                  <ChatMessageView message={m} language={language} />
                </div>
              ))}

              {showStreamingPlaceholder && liveMessageId && (
                <div className="fade-in">
                  <ChatMessageView
                    message={{
                      id: liveMessageId,
                      role: "assistant",
                      content: liveAnswer,
                    }}
                    language={language}
                    liveTrace={{ entries: liveTrace, isLive: true }}
                    isStreaming
                  />
                </div>
              )}

              {showEnsembleLoading && (
                <div className="fade-in flex items-center gap-3 px-4 py-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)]">
                  <span className="block w-3 h-3 rounded-full border-2 border-[var(--accent)] border-t-transparent animate-spin" />
                  <div className="text-xs text-[var(--fg-secondary)]">
                    Asking 3 models in parallel and judging the responses…
                  </div>
                </div>
              )}

              <div ref={scrollAnchorRef} />
            </div>
          )}
        </div>

        <div className="sticky bottom-0 pt-4 pb-6 bg-gradient-to-t from-[var(--bg-base)] via-[var(--bg-base)]/95 to-transparent">
          <Composer
            onSubmit={handleSubmit}
            onAttachFile={handleAttachFile}
            onTranscribe={handleTranscribe}
            pendingAttachment={pendingAttachment}
            onRemoveAttachment={() => setPendingAttachment(null)}
            attaching={attaching}
            busy={busy}
            prefill={prefill}
          />
          <div className="mt-2 text-center text-[0.65rem] text-[var(--fg-muted)] font-mono">
            shift + enter for newline · drag a file in to attach ·{" "}
            {ensembleEnabled
              ? "multi-LLM mode"
              : mode === "agent"
                ? "agent mode (multi-step + tools)"
                : "RAG mode"}
          </div>
        </div>
      </main>
    </div>
  );
}