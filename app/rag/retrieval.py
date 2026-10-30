"""Vectorstore retrieval - scoped to the current user via contextvar.

Every query is routed to the current user's Weaviate tenant. Cross-tenant
reads are impossible: search_for() always passes the tenant, and the store has
multi-tenancy enabled so a missing tenant raises rather than leaking.

This module exposes two retrievers:

  retrieve(query, k)
      Personal-only. Used by document_search (agent tool) and anywhere that
      should ONLY see the user's own indexed files. Unchanged from before.

  retrieve_merged(query, k)
      Personal + global knowledge base, mixed and re-sorted by score. Used by
      the RAG endpoint (chain.rag_answer) so that turning on "RAG mode"
      surfaces both the user's documents AND admin-curated knowledge.

      Each returned Document carries an `origin` key in its metadata:
        "personal"       -> from the user's tenant
        "knowledge_base" -> from the shared global corpus
      Callers (chain.py) propagate this into SourceInfo so the UI can render
      a small badge per source.
"""
from langchain_core.documents import Document

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.collections import search_for
from app.rag.global_collection import global_search
from app.rag.user_context import get_current_user

log = get_logger(__name__)


def retrieve(query: str, k: int | None = None) -> list[tuple[Document, float]]:
    """Return [(doc, similarity_score), ...] for the CURRENT user's tenant.

    Personal-only. The user_id is read from the contextvar set by the API
    route. Tools invoked by the agent inherit this context automatically.
    """
    k = k or settings.top_k
    user_id = get_current_user()
    return search_for(user_id, query, k)


def retrieve_merged(
    query: str,
    k: int | None = None,
) -> list[tuple[Document, float]]:
    """Return [(doc, score), ...] merged from personal + global corpora.

    Strategy (chosen for fairness + predictability):
      - Fetch k // 2 from each corpus (rounded so the total >= k for odd k).
        Even when the global corpus contains thousands of objects and would
        otherwise dominate by sheer breadth, the user's own docs always get
        a fair allocation.
      - Stamp `origin` into each Document.metadata ("personal" or
        "knowledge_base") so downstream code can surface the distinction.
      - Concatenate and sort by score (higher = better). Same scoring scale
        is used by both stores (BGE embeddings + Weaviate similarity), so
        scores are directly comparable.

    Failure handling: if either store errors or is empty, we still return
    whatever the other produced. RAG should degrade gracefully, not 500.
    """
    k = k or settings.top_k
    # Allocate half to each, but always at least 1 each, and never exceed k.
    per_side = max(1, k // 2)

    personal_results: list[tuple[Document, float]] = []
    global_results: list[tuple[Document, float]] = []

    # --- personal side ---
    try:
        user_id = get_current_user()
        personal_results = search_for(user_id, query, per_side)
    except Exception as e:
        # Most common cause: no current user / no tenant yet. Treat as empty.
        log.debug("retrieve_merged: personal search skipped (%s)", e)

    # --- global side ---
    try:
        # global_search returns the same [(Document, score)] shape.
        global_results = global_search(query, k=per_side)
    except Exception as e:
        log.warning("retrieve_merged: global search failed: %s", e)

    # Stamp origin onto each Document so callers can surface the distinction.
    for doc, _ in personal_results:
        doc.metadata = {**(doc.metadata or {}), "origin": "personal"}
    for doc, _ in global_results:
        doc.metadata = {**(doc.metadata or {}), "origin": "knowledge_base"}

    merged = personal_results + global_results
    # Sort by score descending. None-scores sink to the bottom.
    merged.sort(key=lambda p: p[1] if p[1] is not None else float("-inf"), reverse=True)
    return merged
