/**
 * Shared types matching the FastAPI backend's Pydantic schemas.
 */

export type Provider = "GROQ" | "OLLAMA" | string;

export interface SourceInfo {
  source_file: string;
  page: number | null;
  snippet: string;
  score: number | null;
  // Origin of this chunk:
  //   "personal"       -> the user's own indexed documents
  //   "knowledge_base" -> the shared/global knowledge base (admin-curated)
  // Optional + default-to-personal for backward compatibility with older
  // responses that don't include this field.
  origin?: "personal" | "knowledge_base";
}

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  result_preview: string | null;
}

export interface AgentResponse {
  answer: string;
  sources: SourceInfo[];
  tool_calls: ToolCall[];
  session_id: string;
  latency_ms: number;
}

export interface QueryResponse {
  answer: string;
  sources: SourceInfo[];
  latency_ms: number;
}

export interface AttachmentResponse {
  filename: string;
  text: string;
  method: string;
  pages_processed: number;
  size_bytes: number;
  char_count: number;
}

export interface TranscribeResponse {
  text: string;
  language: string | null;
  duration_sec: number | null;
}

// Streaming events from /agent/stream
export type StreamEvent =
  | { type: "tool_start"; name: string; args: Record<string, unknown> }
  | { type: "tool_end"; name: string; preview: string }
  | { type: "token"; delta: string }
  | { type: "done"; answer: string; sources: SourceInfo[]; tool_calls: ToolCall[]; session_id: string; latency_ms: number }
  | { type: "error"; message: string };

// Multi-LLM ensemble (defined inline to avoid circular imports with api.ts)
export interface EnsembleData {
  question: string;
  candidates: {
    model: string;
    answer: string;
    latency_ms: number;
    error: string | null;
  }[];
  ranking: { model: string; rank: number; reason: string }[];
  verdict: string;
  judge_model: string;
  total_latency_ms: number;
}

// Local-only chat message used by the UI
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  attachmentName?: string;
  sources?: SourceInfo[];
  toolCalls?: ToolCall[];
  trace?: TraceEntry[];
  latencyMs?: number;
  ensemble?: EnsembleData;
}

export interface TraceEntry {
  name: string;
  args: Record<string, unknown>;
  preview?: string;
  status: "running" | "done";
}

export type Mode = "agent" | "rag";

/* =============================================================================
 * Admin types (backend: app/api/admin_routes.py)
 * ============================================================================= */

export type UserRole = "user" | "corpus_admin" | "super_admin";

export interface AdminUserInfo {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  display_name: string | null;
  created_at: string | null;  // ISO string from backend
}

// Structured corpus item (mirrors CorpusItem on the backend).
// Generic core - only `text` is required; everything else is optional metadata.
// content_type is free-form ("document", "policy", "manual", "faq", ...).
export interface CorpusItemInput {
  text: string;
  content_type?: string;
  source_title?: string;
  book_title?: string;
  author?: string;
  language?: string;
  volume?: string;
  topic?: string;
  page?: string;
}

export interface CorpusIngestResponse {
  inserted: number;
  total_in_corpus: number;
  message: string;
}

export interface CorpusStats {
  total: number;
}

export interface SystemStats {
  total_users: number;
  corpus_total: number;
}

// One source in the KB (group of chunks sharing a source_title)
export interface CorpusSourceInfo {
  source_title: string;
  content_type: string;
  chunk_count: number;
}

// One hit returned by the admin /corpus/search preview
export interface CorpusSearchHit {
  text: string;
  score: number;

  source_title: string | null;
  content_type: string | null;
  author: string | null;
  page: string | null;
}

export interface CorpusSearchResponse {
  hits: CorpusSearchHit[];
}