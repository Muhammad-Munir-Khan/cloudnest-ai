"""Agent endpoints (multi-turn, tool-enabled, streaming or batch, ensemble).

All endpoints require an authenticated user via JWT.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent import storage
from app.agent.ensemble import EnsembleResponse, run_ensemble_async
from app.agent.graph import run_agent, stream_agent
from app.api.errors import error_reference, internal_error, log_error
from app.core.auth import current_active_user
from app.core.schemas import AgentRequest, AgentResponse
from app.models.user import User

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat", response_model=AgentResponse)
def chat(req: AgentRequest, user: User = Depends(current_active_user)):
    try:
        return run_agent(
            req.message,
            req.session_id,
            attachment_text=req.attachment_text,
            attachment_name=req.attachment_name,
            language=req.language,
            user_id=user.id,
        )
    except Exception as e:
        raise internal_error("Agent failed", e) from e


@router.post("/stream")
def chat_stream(req: AgentRequest, user: User = Depends(current_active_user)):
    user_id = user.id  # capture before generator starts (user object out of scope)

    def event_stream():
        try:
            for event in stream_agent(
                req.message,
                req.session_id,
                attachment_text=req.attachment_text,
                attachment_name=req.attachment_name,
                language=req.language,
                user_id=user_id,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            ref = error_reference()
            log_error("agent stream failed", e, ref)
            err = {"type": "error", "message": f"Agent failed. Reference: {ref}"}
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Multi-LLM ensemble ----------------------------------------------------

class EnsembleRequest(BaseModel):
    message: str = Field(..., min_length=1)
    language: str = "en"


@router.post("/ensemble", response_model=EnsembleResponse)
async def ensemble(
    req: EnsembleRequest,
    user: User = Depends(current_active_user),
):
    """Multi-LLM mode: fan out to several Groq models, judge their responses.

    Doesn't write to storage, but still requires auth so we can rate-limit
    per user later (Phase 3).
    """
    try:
        return await run_ensemble_async(req.message, language=req.language)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise internal_error("Ensemble failed", e) from e


# --- Session management ----------------------------------------------------

class SessionInfo(BaseModel):
    id: str
    title: str
    created_at: float
    updated_at: float
    message_count: int = 0


class StoredMessage(BaseModel):
    id: int
    role: str
    content: str
    created_at: float
    metadata: dict | None = None


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


@router.get("/sessions", response_model=list[SessionInfo])
def list_sessions(user: User = Depends(current_active_user)):
    return storage.list_sessions(limit=200, user_id=user.id)


@router.get("/sessions/{session_id}/messages", response_model=list[StoredMessage])
def get_session_messages(
    session_id: str,
    user: User = Depends(current_active_user),
):
    if not storage.get_session(session_id, user_id=user.id):
        raise HTTPException(status_code=404, detail="Session not found")
    return storage.list_messages(session_id, user_id=user.id)


@router.post("/sessions/{session_id}", response_model=SessionInfo)
def create_session_endpoint(
    session_id: str,
    user: User = Depends(current_active_user),
):
    existing = storage.get_session(session_id, user_id=user.id)
    if existing:
        return existing
    return storage.create_session(session_id=session_id, user_id=user.id)


@router.patch("/sessions/{session_id}", response_model=SessionInfo)
def rename_session_endpoint(
    session_id: str,
    req: RenameRequest,
    user: User = Depends(current_active_user),
):
    if not storage.rename_session(session_id, req.title, user_id=user.id):
        raise HTTPException(status_code=404, detail="Session not found")
    sess = storage.get_session(session_id, user_id=user.id)
    if not sess:
        raise HTTPException(status_code=500, detail="Inconsistent state")
    return sess


@router.delete("/sessions/{session_id}")
def delete_session_endpoint(
    session_id: str,
    user: User = Depends(current_active_user),
):
    deleted = storage.delete_session(session_id, user_id=user.id)
    return {"status": "deleted" if deleted else "not_found", "session_id": session_id}
