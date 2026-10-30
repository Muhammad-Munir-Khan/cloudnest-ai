"""Shared global knowledge base on Weaviate.

This is the SHARED corpus (admin-curated documents, manuals, policies, books,
etc.) that every user can read. It is deliberately SEPARATE from the per-user
multi-tenant collection (`CloudNestDocs` in app/rag/collections.py):

  - Per-user RAG  -> collection CloudNestDocs, multi-tenancy ON, one tenant per
                     user, write+read scoped to the owning user.
  - Global RAG    -> collection GlobalKnowledgeBase, multi-tenancy OFF,
                     world-readable, admin-write-only. THIS FILE.

Why a separate collection (not a "global tenant"): the access model is
fundamentally different (shared vs isolated). Keeping them in distinct
collections makes the security boundary explicit at the storage layer rather
than relying on tenant-filter discipline at every read.

Content model:
  Each object has a `content_type` (free-form label - "document", "policy",
  "manual", "faq", "report", or whatever your admins decide to use). It is
  used for filtering only; nothing in the code enforces a fixed taxonomy.

Schema (generic core, used by every object):
  text          - the searchable body content
  content_type  - free-form category label (filterable)
  source_title  - human-readable name of the source document/book/article
  language      - ISO code, optional
  author        - optional attribution
  book_title    - longer/canonical title if different from source_title
  volume        - optional (multi-volume references)
  topic         - optional subject tag
  page          - optional page reference (stored as text; pagination varies)
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.documents import Document

from app.core.logging import get_logger
from app.rag.collections import get_weaviate_client
from app.rag.embeddings import get_embeddings

log = get_logger(__name__)

# Collection name (Weaviate class). Lives in its own dedicated collection
# rather than a shared tenant so the security boundary - "anyone can read,
# only admins can write" - is enforced at the storage layer.
GLOBAL_INDEX = "GlobalKnowledgeBase"


def _build_schema_properties():
    """The explicit, typed schema for the global corpus.

    Deliberately small: a generic core of fields that fit any reference
    material (documents, manuals, policies, books). `text` is the embedded,
    searchable field. All other fields are TEXT and optional - chunks set
    only the fields that apply to them.
    """
    from weaviate.classes.config import DataType, Property

    return [
        # body + filterable category
        Property(name="text", data_type=DataType.TEXT),            # searchable content
        Property(name="content_type", data_type=DataType.TEXT),    # free-form category label
        # source identity / attribution
        Property(name="source_title", data_type=DataType.TEXT),    # human-readable source name
        Property(name="book_title", data_type=DataType.TEXT),      # canonical title if different
        Property(name="author", data_type=DataType.TEXT),
        Property(name="language", data_type=DataType.TEXT),
        # locator (optional)
        Property(name="volume", data_type=DataType.TEXT),
        Property(name="topic", data_type=DataType.TEXT),
        Property(name="page", data_type=DataType.TEXT),
    ]


def ensure_global_collection() -> None:
    """Create the global knowledge-base collection if it doesn't exist.

    Multi-tenancy OFF (shared/world-readable). BYO vectors (BGE), so no
    vectorizer module. Idempotent - safe to call repeatedly.
    """
    client = get_weaviate_client()
    if client.collections.exists(GLOBAL_INDEX):
        return
    from weaviate.classes.config import Configure
    client.collections.create(
        name=GLOBAL_INDEX,
        properties=_build_schema_properties(),
        vectorizer_config=Configure.Vectorizer.none(),
        inverted_index_config=Configure.inverted_index(
            # enable BM25 for hybrid search
            bm25_b=0.75,
            bm25_k1=1.2,
        ),
    )
    log.info("created global collection %s (shared, BYO vectors, BM25 on)", GLOBAL_INDEX)


@lru_cache(maxsize=1)
def _embedder():
    return get_embeddings()


def add_to_global_corpus(items: list[dict[str, Any]]) -> int:
    """Bulk-add structured content to the global corpus.

    Each item is a dict with at least {"text": ...} plus any metadata fields
    from the schema (content_type, source_title, author, page, ...). Unknown
    keys are ignored by Weaviate's typed schema. We compute the BGE
    embedding for each item's `text` ourselves (BYO vectors).

    Returns the number of objects inserted. Single entry point all loaders
    (PDF parser, structured ingest, future loaders) feed into.
    """
    if not items:
        return 0
    ensure_global_collection()
    client = get_weaviate_client()
    coll = client.collections.get(GLOBAL_INDEX)

    embedder = _embedder()
    texts = [it.get("text", "") for it in items]
    vectors = embedder.embed_documents(texts)

    inserted = 0
    with coll.batch.dynamic() as batch:
        for it, vec in zip(items, vectors, strict=True):
            # content_type is free-form (e.g. "document", "policy", "manual", ...).
            # Default to "document" if missing; lowercased for consistent filtering.
            props = dict(it)
            ct = str(props.get("content_type", "document")).lower()
            props["content_type"] = ct
            batch.add_object(properties=props, vector=vec)
            inserted += 1
    log.info("added %d objects to global corpus", inserted)
    return inserted


def _filters_from(content_type: str | None):
    """Build a Weaviate filter from an optional content_type constraint."""
    from weaviate.classes.query import Filter

    if not content_type:
        return None
    return Filter.by_property("content_type").equal(content_type.lower())


def global_search(
    query: str,
    k: int = 5,
    content_type: str | None = None,
    alpha: float = 0.5,
) -> list[tuple[Document, float]]:
    """Hybrid (BM25 + vector) search over the global corpus.

    alpha: 0.0 = pure keyword (BM25), 1.0 = pure vector, 0.5 = balanced hybrid.
    Optional content_type narrows to a single category. Returns
    [(Document, score)] where Document.metadata carries the per-object fields
    so callers can cite precisely.
    """
    client = get_weaviate_client()
    if not client.collections.exists(GLOBAL_INDEX):
        return []
    coll = client.collections.get(GLOBAL_INDEX)

    query_vec = _embedder().embed_query(query)
    filters = _filters_from(content_type)

    from weaviate.classes.query import MetadataQuery
    res = coll.query.hybrid(
        query=query,
        vector=query_vec,
        alpha=alpha,
        limit=k,
        filters=filters,
        return_metadata=MetadataQuery(score=True),
    )

    out: list[tuple[Document, float]] = []
    for obj in res.objects:
        props = obj.properties or {}
        text = props.get("text", "")
        score = 0.0
        if obj.metadata and obj.metadata.score is not None:
            score = float(obj.metadata.score)
        # everything except the body text becomes citation metadata
        meta = {key: val for key, val in props.items() if key != "text"}
        out.append((Document(page_content=text, metadata=meta), score))
    return out


def global_corpus_count() -> int:
    """Total objects in the global corpus (0 if not created yet)."""
    try:
        client = get_weaviate_client()
        if not client.collections.exists(GLOBAL_INDEX):
            return 0
        coll = client.collections.get(GLOBAL_INDEX)
        return coll.aggregate.over_all(total_count=True).total_count
    except Exception as e:
        log.debug("global_corpus_count failed: %s", e)
        return 0


def list_sources() -> list[dict]:
    """Group corpus objects by source_title and return a summary per source.

    Returns:
        list of {source_title, content_type, chunk_count}. Empty list if the
        collection doesn't exist yet or aggregation fails.

    Note: Weaviate v4's group_by aggregation returns one bucket per distinct
    value of the group key. We additionally take the first object in each
    bucket to surface its content_type (since chunks from one source typically
    share the same content_type).
    """
    try:
        client = get_weaviate_client()
        if not client.collections.exists(GLOBAL_INDEX):
            return []
        coll = client.collections.get(GLOBAL_INDEX)

        from weaviate.classes.aggregate import GroupByAggregate

        agg = coll.aggregate.over_all(
            group_by=GroupByAggregate(prop="source_title"),
            total_count=True,
        )

        results: list[dict] = []
        # agg.groups is a list of grouped aggregation results
        for group in getattr(agg, "groups", []) or []:
            source_title = group.grouped_by.value if group.grouped_by else "(unknown)"
            count = group.total_count or 0
            # Best-effort: fetch one object from this source for content_type.
            content_type = _peek_content_type(coll, source_title)
            results.append({
                "source_title": source_title or "(untitled)",
                "content_type": content_type or "document",
                "chunk_count": int(count),
            })

        # Sort: most chunks first
        results.sort(key=lambda r: r["chunk_count"], reverse=True)
        return results
    except Exception as e:
        log.exception("list_sources failed: %s", e)
        return []


def _peek_content_type(coll, source_title: str) -> str | None:
    """Fetch one object from a source to read its content_type."""
    if not source_title:
        return None
    try:
        from weaviate.classes.query import Filter
        res = coll.query.fetch_objects(
            filters=Filter.by_property("source_title").equal(source_title),
            limit=1,
            return_properties=["content_type"],
        )
        for obj in res.objects:
            return (obj.properties or {}).get("content_type")
    except Exception:
        pass
    return None


def delete_by_source(source_title: str) -> int:
    """Delete every corpus object whose source_title matches exactly.

    Returns the number of objects deleted. 0 if the collection doesn't exist
    or no objects match. Used by the admin "delete source" action.
    """
    if not source_title:
        return 0
    try:
        client = get_weaviate_client()
        if not client.collections.exists(GLOBAL_INDEX):
            return 0
        coll = client.collections.get(GLOBAL_INDEX)

        from weaviate.classes.query import Filter

        # source_title is word-tokenized by Weaviate, so the equal filter alone
        # also matches "Annual Report" for "Report". Keep exact matches only.
        found = coll.query.fetch_objects(
            filters=Filter.by_property("source_title").equal(source_title),
            limit=10000,
            return_properties=["source_title"],
        )
        ids = [o.uuid for o in found.objects
               if (o.properties or {}).get("source_title") == source_title]
        if not ids:
            return 0
        result = coll.data.delete_many(where=Filter.by_id().contains_any(ids))
        # delete_many returns DeleteManyReturn with .matches / .successful
        deleted = int(getattr(result, "successful", 0) or getattr(result, "matches", 0) or 0)
        log.info("deleted %d objects from corpus where source_title=%r", deleted, source_title)
        return deleted
    except Exception as e:
        log.exception("delete_by_source failed for %r: %s", source_title, e)
        return 0
