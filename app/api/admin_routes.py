"""Admin endpoints - user management + global knowledge base management.

All routes are gated by role (app/core/admin_deps.py):
  - corpus_admin or higher: corpus ingest/stats/sources/search
  - super_admin only:        user listing, role changes, activate/deactivate,
                             edit details, send reset, force logout

Mounted in main.py with: app.include_router(admin_routes.router)
The router already carries the /admin prefix.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi_users import BaseUserManager
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.uploads import read_upload_limited
from app.core.admin_deps import require_corpus_admin, require_super_admin
from app.core.audit import audit_event
from app.core.auth import get_user_manager
from app.core.db import get_async_session
from app.core.email import (
    account_deleted_email,
    account_suspended_email,
    account_unsuspended_email,
    send_email,
)
from app.core.logging import get_logger
from app.core.roles import UserRole
from app.models.user import User
from app.rag.collections import (
    delete_user_collection,
    delete_user_docs_dir,
)
from app.rag.global_collection import (
    add_to_global_corpus,
    delete_by_source,
    global_corpus_count,
    global_search,
    list_sources,
)

log = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB cap for corpus files


# =============================================================================
# Schemas
# =============================================================================

class AdminUserInfo(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    is_verified: bool
    display_name: str | None = None
    created_at: datetime | None = None


class RoleUpdateRequest(BaseModel):
    role: UserRole


class ActiveUpdateRequest(BaseModel):
    is_active: bool
    # Optional reason shown to the user in the suspension email. Free-form
    # text. Ignored when is_active=True (unblock). We do NOT persist this -
    # it lives only in the email body, per the v1 product decision.
    reason: str | None = Field(None, max_length=1000)


class UserDetailsUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=80)  # users.display_name is String(80)


class CorpusItem(BaseModel):
    """One structured item to ingest into the global corpus.

    Generic core: only `text` is required. Everything else is optional
    metadata that gets stored alongside the chunk for filtering and
    citation. Free-form `content_type` so admins can categorize content
    however suits their use case ("document", "policy", "manual", "faq", ...).
    """
    text: str = Field(..., min_length=1, max_length=100_000)
    content_type: str = Field("document", max_length=100)
    source_title: str | None = None
    book_title: str | None = None
    author: str | None = None
    language: str | None = None
    volume: str | None = None
    topic: str | None = None
    page: str | None = None


class CorpusIngestRequest(BaseModel):
    items: list[CorpusItem] = Field(..., min_length=1, max_length=1000)


class CorpusIngestResponse(BaseModel):
    inserted: int
    total_in_corpus: int
    message: str


class CorpusStats(BaseModel):
    total: int


class SystemStats(BaseModel):
    total_users: int
    corpus_total: int


# =============================================================================
# User management (super_admin only)
# =============================================================================

@router.get("/users", response_model=list[AdminUserInfo])
async def list_users(
    admin: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_async_session),
):
    """List all users with their roles. Super-admin only."""
    result = await session.execute(select(User))
    users = result.scalars().unique().all()
    return [
        AdminUserInfo(
            id=u.id,
            email=u.email,
            role=getattr(u, "role", UserRole.user.value),
            is_active=u.is_active,
            is_verified=u.is_verified,
            display_name=getattr(u, "display_name", None),
            created_at=getattr(u, "created_at", None),
        )
        for u in users
    ]


@router.patch("/users/{user_id}/role", response_model=AdminUserInfo)
async def set_user_role(
    user_id: uuid.UUID,
    req: RoleUpdateRequest,
    admin: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_async_session),
):
    """Change a user's role. Super-admin only.

    Keeps is_superuser in sync (super_admin <-> True) directly here, since this
    updates the DB row outside the fastapi-users manager flow.
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().unique().one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin.id and req.role != UserRole.super_admin:
        raise HTTPException(
            status_code=400,
            detail="You cannot change your own super_admin role.",
        )

    old_role = getattr(user, "role", UserRole.user.value)
    is_super = req.role == UserRole.super_admin
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(role=req.role.value, is_superuser=is_super)
    )
    await session.commit()
    audit_event("user.role_change", actor=admin.email, target=user.email,
                old_role=old_role, new_role=req.role.value)

    return AdminUserInfo(
        id=user.id,
        email=user.email,
        role=req.role.value,
        is_active=user.is_active,
        is_verified=user.is_verified,
        display_name=getattr(user, "display_name", None),
        created_at=getattr(user, "created_at", None),
    )


@router.patch("/users/{user_id}/active", response_model=AdminUserInfo)
async def set_user_active(
    user_id: uuid.UUID,
    req: ActiveUpdateRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_async_session),
):
    """Block or unblock a user. Super-admin only.

    On block (is_active=False):
      - sets is_active=False
      - sets jwt_invalidated_at=now() in the SAME UPDATE so any live session
        dies on the next request (block implies force-logout - we don't want
        a blocked user to keep chatting until they happen to close the tab)
      - schedules an "account suspended" email with the optional reason

    On unblock (is_active=True):
      - sets is_active=True (jwt_invalidated_at left as-is so they don't have
        to log in again if they happened to still be using a valid token,
        though typically the suspension cleared it already)
      - schedules an "account restored" email

    Self-protection: an admin cannot deactivate themselves (lockout risk).
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().unique().one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin.id and not req.is_active:
        raise HTTPException(
            status_code=400, detail="You cannot deactivate your own account."
        )

    if not req.is_active:
        # BLOCK: flip is_active AND set jwt_invalidated_at in one transaction.
        now = datetime.now(timezone.utc)
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_active=False, jwt_invalidated_at=now)
        )
        await session.commit()
        log.info(
            "admin %s blocked %s (reason=%r)",
            admin.email, user.email, (req.reason or "").strip() or None,
        )
        audit_event("user.suspend", actor=admin.email, target=user.email,
                    reason=(req.reason or "").strip() or None)
        # Email asynchronously - never block the API on SMTP latency.
        subject, html_body, text_body = account_suspended_email(req.reason)
        background_tasks.add_task(
            send_email, user.email, subject, html_body, text_body
        )
    else:
        # UNBLOCK: just flip is_active. Don't touch jwt_invalidated_at - if it
        # was set by the prior block, it stays set, which is correct: any
        # pre-block JWTs are still invalid. The user gets a fresh JWT on next
        # login.
        await session.execute(
            update(User).where(User.id == user_id).values(is_active=True)
        )
        await session.commit()
        log.info("admin %s unblocked %s", admin.email, user.email)
        audit_event("user.unsuspend", actor=admin.email, target=user.email)
        subject, html_body, text_body = account_unsuspended_email()
        background_tasks.add_task(
            send_email, user.email, subject, html_body, text_body
        )

    return AdminUserInfo(
        id=user.id,
        email=user.email,
        role=getattr(user, "role", UserRole.user.value),
        is_active=req.is_active,
        is_verified=user.is_verified,
        display_name=getattr(user, "display_name", None),
        created_at=getattr(user, "created_at", None),
    )


@router.patch("/users/{user_id}", response_model=AdminUserInfo)
async def edit_user_details(
    user_id: uuid.UUID,
    req: UserDetailsUpdate,
    admin: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_async_session),
):
    """Edit a user's display name. Super-admin only.

    Email is intentionally NOT editable here (login identity + tied to OAuth).
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().unique().one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    await session.execute(
        update(User).where(User.id == user_id).values(display_name=req.display_name)
    )
    await session.commit()
    audit_event("user.edit", actor=admin.email, target=user.email,
                display_name=req.display_name)

    return AdminUserInfo(
        id=user.id,
        email=user.email,
        role=getattr(user, "role", UserRole.user.value),
        is_active=user.is_active,
        is_verified=user.is_verified,
        display_name=req.display_name,
        created_at=getattr(user, "created_at", None),
    )


@router.post("/users/{user_id}/send-reset")
async def send_password_reset(
    user_id: uuid.UUID,
    admin: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_async_session),
    user_manager: BaseUserManager = Depends(get_user_manager),
):
    """Trigger a password-reset email to the target user. Super-admin only.

    Reuses the fastapi-users forgot_password flow (generates token, calls
    on_after_forgot_password -> our UserManager sends the email).
    """
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().unique().one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        await user_manager.forgot_password(user)
    except Exception as e:
        log.exception("admin-triggered reset failed for %s", user.email)
        raise HTTPException(status_code=500, detail=f"Could not send reset: {e}")

    log.info("admin %s sent password reset to %s", admin.email, user.email)
    audit_event("user.send_reset", actor=admin.email, target=user.email)
    return {"status": "sent", "email": user.email}


@router.post("/users/{user_id}/force-logout")
async def force_logout(
    user_id: uuid.UUID,
    admin: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_async_session),
):
    """Invalidate every JWT issued to the user before NOW. Super-admin only.

    Sets users.jwt_invalidated_at = now(). The fresh-user auth dependency
    rejects any token whose iat predates this timestamp. The user can log
    in again to get a fresh token.

    Self-protection: an admin cannot force-logout themselves (lockout risk).
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=400, detail="You cannot force-logout yourself."
        )

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().unique().one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(timezone.utc)
    await session.execute(
        update(User).where(User.id == user_id).values(jwt_invalidated_at=now)
    )
    await session.commit()

    log.info("admin %s force-logged-out %s", admin.email, user.email)
    audit_event("user.force_logout", actor=admin.email, target=user.email)
    return {"status": "ok", "email": user.email, "invalidated_at": now.isoformat()}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_async_session),
):
    """Hard-delete a user and all their data. Super-admin only.

    Cleanup order is intentional:
      1. Postgres (source of truth) - one transaction, all-or-nothing.
         Order within the transaction: chat_messages -> chat_sessions ->
         oauth_account -> users. Foreign keys would otherwise cascade-block.
      2. Weaviate tenant (best-effort, logged on failure).
      3. On-disk docs folder (best-effort, logged on failure).
      4. Confirmation email (background task, already non-fatal on SMTP failure).

    Reasoning: if Postgres delete succeeds, the user is GONE from the system's
    point of view. Orphan Weaviate or disk data can be cleaned up later by a
    sweep job; the opposite (cleanup succeeded but user row remains) would be
    worse - they'd still be able to log in but their docs/vectors would be
    gone, which is confusing.

    Self-protection: an admin cannot delete themselves (lockout risk).

    Email notification: sent AFTER deletion completes. The email is fire-and-
    forget - if SMTP is down the deletion still succeeds.
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=400, detail="You cannot delete your own account."
        )

    # Look up the user first - we need the email for the confirmation email,
    # and need to verify they actually exist before any cleanup.
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().unique().one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user_email = user.email  # capture before deletion

    # --- Step 1: Postgres deletion (atomic) ---
    # Order matters because of foreign-key constraints. SQLAlchemy core DELETE
    # statements within one session.execute scope all participate in the same
    # transaction that session.commit() seals.
    from sqlalchemy import delete as sa_delete
    from app.models import chat as chat_models  # chat_messages, chat_sessions
    from app.models.user import OAuthAccount

    try:
        # Find the user's sessions so we can scope message deletion to them.
        sessions_q = await session.execute(
            select(chat_models.ChatSession.id).where(
                chat_models.ChatSession.user_id == user_id
            )
        )
        session_ids = [row[0] for row in sessions_q.all()]

        if session_ids:
            await session.execute(
                sa_delete(chat_models.ChatMessage).where(
                    chat_models.ChatMessage.session_id.in_(session_ids)
                )
            )
            await session.execute(
                sa_delete(chat_models.ChatSession).where(
                    chat_models.ChatSession.id.in_(session_ids)
                )
            )

        await session.execute(
            sa_delete(OAuthAccount).where(OAuthAccount.user_id == user_id)
        )
        await session.execute(
            sa_delete(User).where(User.id == user_id)
        )
        await session.commit()
    except Exception as e:
        await session.rollback()
        log.exception("Postgres deletion failed for user %s (%s)", user_id, user_email)
        raise HTTPException(
            status_code=500,
            detail=f"Could not delete user from database: {e}",
        )

    log.info("admin %s hard-deleted user %s (%s) from Postgres", admin.email, user_id, user_email)
    audit_event("user.delete", actor=admin.email, target=user_email)

    # --- Step 2: Weaviate tenant cleanup (best-effort) ---
    # delete_user_collection already swallows + logs exceptions, so this won't
    # raise. We just call it and trust the logging.
    await run_in_threadpool(delete_user_collection, user_id)

    # --- Step 3: Disk cleanup (best-effort) ---
    try:
        await run_in_threadpool(delete_user_docs_dir, user_id)
    except Exception as e:
        log.warning("disk cleanup failed for user %s: %s", user_id, e)

    # --- Step 4: Email the (now-deleted) user ---
    subject, html_body, text_body = account_deleted_email()
    background_tasks.add_task(send_email, user_email, subject, html_body, text_body)

    return {
        "status": "ok",
        "email": user_email,
        "user_id": str(user_id),
    }


# =============================================================================
# Corpus management (corpus_admin or higher)
# =============================================================================

@router.post("/corpus/ingest", response_model=CorpusIngestResponse)
async def ingest_structured(
    req: CorpusIngestRequest,
    admin: User = Depends(require_corpus_admin),
):
    """Ingest structured content (JSON) into the global corpus.

    Each item carries explicit metadata for citation. Use this path for any
    content where you want to set the fields precisely (vs the file upload
    path which infers chunks from a document).
    """
    items = [it.model_dump(exclude_none=True) for it in req.items]
    try:
        inserted = await run_in_threadpool(add_to_global_corpus, items)
    except Exception as e:
        log.exception("corpus ingest failed")
        raise HTTPException(status_code=500, detail=f"Ingest failed: {e}")

    total = await run_in_threadpool(global_corpus_count)
    log.info("admin %s ingested %d items into global corpus", admin.email, inserted)
    audit_event("kb.ingest", actor=admin.email, items=inserted, total=total)
    return CorpusIngestResponse(
        inserted=inserted,
        total_in_corpus=total,
        message=f"Ingested {inserted} items. Corpus now holds {total}.",
    )


@router.post("/corpus/upload", response_model=CorpusIngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    content_type: str = "document",
    source_title: str | None = None,
    author: str | None = None,
    admin: User = Depends(require_corpus_admin),
):
    """Ingest a document file into the global knowledge base.

    Accepts any file type the per-user RAG handles (.pdf, .txt, .md, .docx).
    The file is parsed + chunked using the same loaders as per-user RAG, then
    each chunk is embedded and inserted into the global corpus with the
    metadata you pass (content_type, source_title, author).

    content_type is free-form: pass whatever label suits your knowledge base
    (e.g. "document", "policy", "manual", "faq", "report", ...).
    """
    from app.rag.ingestion import SUPPORTED_EXTENSIONS, _load_one, chunk_documents
    import tempfile

    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    safe_name = Path(file.filename).name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {suffix}. "
                   f"Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    data = await read_upload_limited(file, MAX_UPLOAD_BYTES)
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    tmp_path = Path(tempfile.gettempdir()) / safe_name
    tmp_path.write_bytes(data)
    def _parse_and_insert() -> int:
        # Parsing, chunking and embedding are blocking; run in a thread.
        raw = _load_one(tmp_path)
        chunks = chunk_documents(raw)
        items = [
            {
                "text": c.page_content,
                "content_type": content_type,
                "source_title": source_title or safe_name,
                "author": author,
                "page": str(c.metadata.get("page", "")),
            }
            for c in chunks
        ]
        return add_to_global_corpus(items)

    try:
        inserted = await run_in_threadpool(_parse_and_insert)
    except Exception as e:
        log.exception("file ingest failed: %s", safe_name)
        raise HTTPException(status_code=500, detail=f"Ingest failed: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    total = await run_in_threadpool(global_corpus_count)
    log.info("admin %s ingested %s (%d chunks)", admin.email, safe_name, inserted)
    audit_event("kb.upload", actor=admin.email, target=safe_name, chunks=inserted)
    return CorpusIngestResponse(
        inserted=inserted,
        total_in_corpus=total,
        message=f"Ingested {inserted} chunks from {safe_name}. Corpus now holds {total}.",
    )


@router.get("/corpus/stats", response_model=CorpusStats)
async def corpus_stats(admin: User = Depends(require_corpus_admin)):
    """Total objects in the global corpus."""
    return CorpusStats(total=await run_in_threadpool(global_corpus_count))


class CorpusSourceInfo(BaseModel):
    source_title: str
    content_type: str
    chunk_count: int


class CorpusSearchHit(BaseModel):
    text: str
    score: float
    source_title: str | None = None
    content_type: str | None = None
    author: str | None = None
    page: str | None = None


class CorpusSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    k: int = 8
    content_type: str | None = Field(None, max_length=100)
    alpha: float = Field(0.5, ge=0.0, le=1.0)


class CorpusSearchResponse(BaseModel):
    hits: list[CorpusSearchHit]


@router.get("/corpus/sources", response_model=list[CorpusSourceInfo])
async def corpus_sources(admin: User = Depends(require_corpus_admin)):
    """List every source in the knowledge base (grouped by source_title).

    Shows how many chunks each source contributed + its content_type. Sorted
    most-chunks-first. Empty list if the corpus is empty or aggregation
    fails (logs a warning).
    """
    rows = await run_in_threadpool(list_sources)
    return [CorpusSourceInfo(**r) for r in rows]


@router.delete("/corpus/sources")
async def delete_corpus_source(
    source_title: str,
    admin: User = Depends(require_corpus_admin),
):
    """Delete every chunk whose source_title matches exactly. corpus_admin+.

    `source_title` comes as a query parameter (not a path segment) because
    titles can contain slashes and arbitrary punctuation.
    """
    if not source_title or not source_title.strip():
        raise HTTPException(status_code=400, detail="source_title required")
    deleted = await run_in_threadpool(delete_by_source, source_title)
    log.info("admin %s deleted source %r (%d chunks)", admin.email, source_title, deleted)
    audit_event("kb.delete", actor=admin.email, target=source_title, deleted=deleted)
    return {"source_title": source_title, "deleted": deleted}


@router.post("/corpus/search", response_model=CorpusSearchResponse)
async def search_corpus(
    req: CorpusSearchRequest,
    admin: User = Depends(require_corpus_admin),
):
    """Hybrid (BM25 + vector) search over the knowledge base.

    Admin-only search/preview tool: lets you sanity-check what's retrievable
    for a query. Uses the same `global_search` your RAG agent uses.

    alpha: 0.0 = pure keyword, 1.0 = pure vector, 0.5 = balanced.
    """
    results = await run_in_threadpool(
        global_search,
        query=req.query,
        k=max(1, min(req.k, 50)),
        content_type=req.content_type,
        alpha=req.alpha,
    )
    hits: list[CorpusSearchHit] = []
    for doc, score in results:
        meta = doc.metadata or {}
        hits.append(CorpusSearchHit(
            text=doc.page_content,
            score=float(score),
            source_title=meta.get("source_title"),
            content_type=meta.get("content_type"),
            author=meta.get("author"),
            page=str(meta.get("page", "")) or None,
        ))
    return CorpusSearchResponse(hits=hits)


# =============================================================================
# System overview
# =============================================================================

@router.get("/stats", response_model=SystemStats)
async def system_stats(
    admin: User = Depends(require_super_admin),
    session: AsyncSession = Depends(get_async_session),
):
    """High-level system stats for the admin dashboard."""
    from sqlalchemy import func
    result = await session.execute(select(func.count()).select_from(User))
    total_users = int(result.scalar() or 0)
    return SystemStats(
        total_users=total_users,
        corpus_total=await run_in_threadpool(global_corpus_count),
    )
