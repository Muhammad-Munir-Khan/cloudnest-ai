/**
 * API client for the FastAPI backend.
 *
 * Every authenticated call goes through apiFetch(), which:
 *   - attaches credentials: "include" so the httpOnly auth cookie is sent
 *   - handles 401 by redirecting the user to /login (with ?next=<currentPath>)
 *
 * Public endpoints (e.g. /health) can call apiFetch too — they just won't
 * trigger the 401 redirect because they don't return 401.
 *
 * Streaming agent endpoint uses fetch + ReadableStream (NOT EventSource,
 * because EventSource cannot send cookies/credentials cross-origin reliably).
 */
import type {
  AdminUserInfo,
  AgentResponse,
  AttachmentResponse,
  CorpusIngestResponse,
  CorpusItemInput,
  CorpusSearchResponse,
  CorpusSourceInfo,
  CorpusStats,
  EnsembleData,
  HealthResponse,
  QueryResponse,
  StreamEvent,
  SystemStats,
  TranscribeResponse,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ------------------------------ Core helper ------------------------------ */

async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(input, {
    ...init,
    credentials: "include",
  });

  if (res.status === 401 && typeof window !== "undefined") {
    const path = window.location.pathname;
    const isPublic =
      path === "/" || path.startsWith("/login") || path.startsWith("/signup");
    if (!isPublic) {
      const next = encodeURIComponent(path + window.location.search);
      window.location.href = `/login?next=${next}`;
    }
  }
  return res;
}

/* ------------------------------ Health ----------------------------------- */

export async function getHealth(): Promise<HealthResponse> {
  const res = await apiFetch(`${API_URL}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Health ${res.status}`);
  return res.json();
}

/* ------------------------------ Documents (per-user RAG) ---------------- */

export interface DocumentInfo {
  filename: string;
  size_bytes: number;
  chunks_indexed: number;
}

export interface UploadResponse {
  filename: string;
  chunks_indexed: number;
  message: string;
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  const res = await apiFetch(`${API_URL}/rag/documents`, { cache: "no-store" });
  if (!res.ok) throw new Error(`List documents ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await apiFetch(`${API_URL}/rag/documents`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch {
      /* noop */
    }
    throw new Error(`Upload failed: ${detail}`);
  }
  return res.json();
}

export async function deleteDocument(filename: string): Promise<void> {
  const res = await apiFetch(
    `${API_URL}/rag/documents/${encodeURIComponent(filename)}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(`Delete document ${res.status}`);
}

export async function reindex(): Promise<{ message: string; chunks_indexed: number }> {
  const res = await apiFetch(`${API_URL}/rag/reindex`, { method: "POST" });
  if (!res.ok) throw new Error(`Reindex ${res.status}: ${await res.text()}`);
  return res.json();
}

/* ------------------------------ RAG -------------------------------------- */

export async function ragQuery(
  question: string,
  language = "en",
): Promise<QueryResponse> {
  const res = await apiFetch(`${API_URL}/rag/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, language }),
  });
  if (!res.ok) throw new Error(`Query ${res.status}: ${await res.text()}`);
  return res.json();
}

/* ------------------------------ Agent ------------------------------------ */

export interface AgentRequestBody {
  message: string;
  session_id: string;
  attachment_text?: string;
  attachment_name?: string;
  language?: string;
}

export async function agentChat(body: AgentRequestBody): Promise<AgentResponse> {
  const res = await apiFetch(`${API_URL}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Agent ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function* streamAgent(
  body: AgentRequestBody,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent, void, unknown> {
  const res = await apiFetch(`${API_URL}/agent/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Stream ${res.status}: ${await res.text().catch(() => "")}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        for (const line of frame.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6);
          try {
            yield JSON.parse(payload) as StreamEvent;
          } catch {
            // Malformed event — ignore.
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/* ------------------------------ Sessions --------------------------------- */

export interface SessionInfo {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
}

export interface StoredMessage {
  id: number;
  role: string;
  content: string;
  created_at: number;
  metadata: Record<string, unknown> | null;
}

export async function listSessions(): Promise<SessionInfo[]> {
  const res = await apiFetch(`${API_URL}/agent/sessions`, { cache: "no-store" });
  if (!res.ok) throw new Error(`List sessions ${res.status}`);
  return res.json();
}

export async function getSessionMessages(
  sessionId: string,
): Promise<StoredMessage[]> {
  const res = await apiFetch(`${API_URL}/agent/sessions/${sessionId}/messages`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Get messages ${res.status}`);
  return res.json();
}

export async function createSession(sessionId: string): Promise<SessionInfo> {
  const res = await apiFetch(`${API_URL}/agent/sessions/${sessionId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Create session ${res.status}`);
  return res.json();
}

export async function renameSession(
  sessionId: string,
  title: string,
): Promise<SessionInfo> {
  const res = await apiFetch(`${API_URL}/agent/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`Rename ${res.status}`);
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiFetch(`${API_URL}/agent/sessions/${sessionId}`, {
    method: "DELETE",
  }).catch(() => {});
}

export const clearSession = deleteSession;

/* ------------------------------ Ensemble (multi-LLM) -------------------- */

export type EnsembleApiResponse = EnsembleData;

export async function ensembleChat(
  message: string,
  language = "en",
): Promise<EnsembleApiResponse> {
  const res = await apiFetch(`${API_URL}/agent/ensemble`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, language }),
  });
  if (!res.ok) throw new Error(`Ensemble ${res.status}: ${await res.text()}`);
  return res.json();
}

/* ------------------------------ Attachments ------------------------------ */

export async function extractAttachment(
  file: File,
): Promise<AttachmentResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await apiFetch(`${API_URL}/attachments/extract`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch {
      /* noop */
    }
    throw new Error(`Attachment failed: ${detail}`);
  }
  return res.json();
}

/* ------------------------------ Voice ------------------------------------ */

export async function transcribe(
  audioBlob: Blob,
  filename = "recording.webm",
): Promise<TranscribeResponse> {
  const formData = new FormData();
  formData.append("file", audioBlob, filename);
  const res = await apiFetch(`${API_URL}/voice/transcribe`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`Transcribe ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function ttsToBlob(
  text: string,
  language = "en",
): Promise<{ blob: Blob; mime: string }> {
  const res = await apiFetch(`${API_URL}/voice/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, language }),
  });
  if (!res.ok) throw new Error(`TTS ${res.status}: ${await res.text()}`);
  const mime = res.headers.get("content-type") || "audio/wav";
  return { blob: await res.blob(), mime };
}

/* =============================================================================
 * ADMIN API  (user management + global knowledge base)
 * All gated server-side by role (app/api/admin_routes.py).
 * ============================================================================= */

/* ------------------------------ Current user ----------------------------- */

export interface MeResponse {
  id: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
  display_name: string | null;
  role: string;
}

export async function getMe(): Promise<MeResponse> {
  const res = await apiFetch(`${API_URL}/users/me`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Me ${res.status}`);
  return res.json();
}

/* ------------------------------ Admin: users ----------------------------- */

export async function adminListUsers(): Promise<AdminUserInfo[]> {
  const res = await apiFetch(`${API_URL}/admin/users`, { cache: "no-store" });
  if (!res.ok) throw new Error(`List users ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function adminSetUserRole(
  userId: string,
  role: string,
): Promise<AdminUserInfo> {
  const res = await apiFetch(`${API_URL}/admin/users/${userId}/role`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* noop */
    }
    throw new Error(`Set role failed: ${detail}`);
  }
  return res.json();
}

export async function adminSetUserActive(
  userId: string,
  isActive: boolean,
  reason?: string,
): Promise<AdminUserInfo> {
  // reason is shown to the user in the suspension email and is ignored
  // server-side when isActive=true (unblock).
  const body: { is_active: boolean; reason?: string } = { is_active: isActive };
  if (!isActive && reason && reason.trim()) {
    body.reason = reason.trim();
  }
  const res = await apiFetch(`${API_URL}/admin/users/${userId}/active`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* noop */
    }
    throw new Error(`Set active failed: ${detail}`);
  }
  return res.json();
}

export async function adminEditUser(
  userId: string,
  displayName: string | null,
): Promise<AdminUserInfo> {
  const res = await apiFetch(`${API_URL}/admin/users/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName }),
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* noop */
    }
    throw new Error(`Edit user failed: ${detail}`);
  }
  return res.json();
}

export async function adminSendReset(
  userId: string,
): Promise<{ status: string; email: string }> {
  const res = await apiFetch(`${API_URL}/admin/users/${userId}/send-reset`, {
    method: "POST",
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* noop */
    }
    throw new Error(`Send reset failed: ${detail}`);
  }
  return res.json();
}

export async function adminForceLogout(
  userId: string,
): Promise<{ status: string; email: string; invalidated_at: string }> {
  const res = await apiFetch(`${API_URL}/admin/users/${userId}/force-logout`, {
    method: "POST",
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* noop */
    }
    throw new Error(`Force logout failed: ${detail}`);
  }
  return res.json();
}

/**
 * Hard-delete a user and all their data (Postgres rows, Weaviate tenant,
 * uploaded files). Permanent and irreversible. The server enforces
 * self-protection: an admin cannot delete their own account.
 */
export async function adminDeleteUser(
  userId: string,
): Promise<{ status: string; email: string; user_id: string }> {
  const res = await apiFetch(`${API_URL}/admin/users/${userId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* noop */
    }
    throw new Error(`Delete user failed: ${detail}`);
  }
  return res.json();
}

/* ------------------------------ Admin: corpus ---------------------------- */

export async function adminIngestCorpus(
  items: CorpusItemInput[],
): Promise<CorpusIngestResponse> {
  const res = await apiFetch(`${API_URL}/admin/corpus/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  if (!res.ok) throw new Error(`Ingest ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function adminUploadCorpusFile(
  file: File,
  contentType = "document",
  sourceTitle?: string,
  author?: string,
): Promise<CorpusIngestResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const params = new URLSearchParams({ content_type: contentType });
  if (sourceTitle) params.set("source_title", sourceTitle);
  if (author) params.set("author", author);

  const res = await apiFetch(
    `${API_URL}/admin/corpus/upload?${params.toString()}`,
    { method: "POST", body: formData },
  );
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* noop */
    }
    throw new Error(`File upload failed: ${detail}`);
  }
  return res.json();
}

// Back-compat alias for any code still calling the old name.
export const adminUploadCorpusPdf = adminUploadCorpusFile;

export async function adminCorpusStats(): Promise<CorpusStats> {
  const res = await apiFetch(`${API_URL}/admin/corpus/stats`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Corpus stats ${res.status}`);
  return res.json();
}

export async function adminListSources(): Promise<CorpusSourceInfo[]> {
  const res = await apiFetch(`${API_URL}/admin/corpus/sources`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`List sources ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function adminDeleteSource(
  sourceTitle: string,
): Promise<{ source_title: string; deleted: number }> {
  const params = new URLSearchParams({ source_title: sourceTitle });
  const res = await apiFetch(
    `${API_URL}/admin/corpus/sources?${params.toString()}`,
    { method: "DELETE" },
  );
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* noop */
    }
    throw new Error(`Delete source failed: ${detail}`);
  }
  return res.json();
}

export async function adminSearchCorpus(
  query: string,
  k = 8,
  contentType?: string,
  alpha = 0.5,
): Promise<CorpusSearchResponse> {
  const res = await apiFetch(`${API_URL}/admin/corpus/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      k,
      content_type: contentType,
      alpha,
    }),
  });
  if (!res.ok) throw new Error(`Search ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function adminSystemStats(): Promise<SystemStats> {
  const res = await apiFetch(`${API_URL}/admin/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error(`System stats ${res.status}`);
  return res.json();
}