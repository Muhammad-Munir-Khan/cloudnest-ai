"""Request and response schemas."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Input bounds. Generous for normal use, but stop unbounded payloads from
# reaching the LLM, embedder or TTS engine.
MAX_MESSAGE_CHARS = 20_000      # chat message / RAG question / TTS text
MAX_ATTACHMENT_CHARS = 50_000   # graph only uses the first 12,000 anyway
MAX_TOP_K = 50
MAX_LANGUAGE_CHARS = 10         # ISO-639 codes like "en", "fil"


# --- Sources / RAG ---

class SourceInfo(BaseModel):
    source_file: str
    page: int | None = None
    snippet: str
    score: float | None = None
    # Origin of this chunk:
    #   "personal"       -> from the current user's own indexed documents
    #   "knowledge_base" -> from the shared/global knowledge base (admin-curated)
    # Default is "personal" so existing call sites that don't set this keep
    # working unchanged.
    origin: Literal["personal", "knowledge_base"] = "personal"


# --- Plain RAG ---

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    top_k: int | None = Field(None, ge=1, le=MAX_TOP_K)
    language: str = Field(
        "en",
        max_length=MAX_LANGUAGE_CHARS,
        description="ISO-639-1 code (e.g., 'en', 'ur', 'ar'). Forces the answer "
                    "into that language even if the question is in English.",
    )


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceInfo]
    latency_ms: int


# --- Ingestion ---

class IngestResponse(BaseModel):
    chunks_indexed: int
    files_processed: int
    message: str


# --- Agent (multi-turn) ---

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class AgentRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    session_id: str = Field(
        ..., max_length=100, description="Stable id grouping a conversation"
    )
    attachment_text: str | None = Field(
        None,
        description="Optional text extracted from an uploaded attachment. "
                    "Prepended to the message as additional context. Truncated "
                    f"to {MAX_ATTACHMENT_CHARS} characters.",
    )
    attachment_name: str | None = Field(None, max_length=255)
    language: str = Field(
        "en",
        max_length=MAX_LANGUAGE_CHARS,
        description="ISO-639-1 code (e.g., 'en', 'ur', 'ar'). Forces the agent "
                    "to respond in that language regardless of the input language.",
    )

    @field_validator("attachment_text")
    @classmethod
    def _truncate_attachment(cls, value: str | None) -> str | None:
        # Truncate rather than reject: extracted text from a large PDF is a
        # normal input, and the agent only reads the first 12,000 chars.
        if value is not None and len(value) > MAX_ATTACHMENT_CHARS:
            return value[:MAX_ATTACHMENT_CHARS]
        return value


class ToolCall(BaseModel):
    name: str
    args: dict
    result_preview: str | None = None


class AgentResponse(BaseModel):
    answer: str
    sources: list[SourceInfo] = []
    tool_calls: list[ToolCall] = []
    session_id: str
    latency_ms: int


# --- Voice ---

class TranscribeResponse(BaseModel):
    text: str
    language: str | None = None
    duration_sec: float | None = None


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    language: str = Field(
        "en",
        max_length=MAX_LANGUAGE_CHARS,
        description="ISO-639-1 code. Selects the matching Edge TTS neural voice.",
    )