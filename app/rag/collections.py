"""Per-user vector storage on Weaviate using native multi-tenancy.

Design
------
A SINGLE Weaviate collection (class) named `settings.weaviate_index_name`
holds every user's documents. Isolation is achieved with Weaviate's native
multi-tenancy: each user is a TENANT, identified by `user_<hex>` (the user's
UUID with dashes stripped) - the same naming we used for Chroma collections.

Each tenant's data lives on its own shard; data in one tenant is never visible
to another. The langchain-weaviate store enforces this: every read/write must
carry a `tenant=` argument, and querying tenant A can only ever return tenant
A's objects.

SECURITY-CRITICAL
-----------------
Tenant isolation is only as good as the tenant argument being passed on EVERY
operation. To make it impossible for a call site to forget, this module is the
single choke point:
  - `tenant_for(user_id)` is the ONLY place the tenant string is computed.
  - `get_user_vectorstore()` returns the shared MT-enabled store; callers MUST
    pass `tenant=tenant_for(user_id)` on each add/search/delete.
  - Helper functions here (add/search/delete/count) wrap that so callers never
    touch a raw store without a tenant.

Never call the underlying store's add/search without a tenant. The library
raises if MT is enabled and no tenant is given, which is the safe failure mode.
"""
from __future__ import annotations

import uuid
from functools import lru_cache
from pathlib import Path

import weaviate
from langchain_weaviate import WeaviateVectorStore

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.embeddings import get_embeddings

log = get_logger(__name__)


def tenant_for(user_id: str | uuid.UUID) -> str:
    """Return the Weaviate tenant name for a user.

    Same scheme as the old Chroma collection name: `user_<32 hex chars>`.
    Tenant names must be stable per user; UUID hex is perfect for that.
    """
    if isinstance(user_id, str):
        user_id = uuid.UUID(user_id)
    return f"user_{user_id.hex}"


def docs_dir_for(user_id: str | uuid.UUID) -> Path:
    """Return the on-disk doc folder for a user. Creates it if missing.

    Unchanged from the Chroma implementation - this is filesystem only and has
    nothing to do with the vector store.
    """
    if isinstance(user_id, str):
        user_id = uuid.UUID(user_id)
    path = settings.docs_dir / user_id.hex
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def get_weaviate_client() -> weaviate.WeaviateClient:
    """Connect to the Weaviate server (cached singleton).

    Uses the v4 client. Host/port come from settings.weaviate_url, parsed into
    the connect_to_custom parameters the v4 client expects.
    """
    from urllib.parse import urlparse

    parsed = urlparse(settings.weaviate_url)
    host = parsed.hostname or "localhost"
    http_port = parsed.port or 8080
    grpc_port = settings.weaviate_grpc_port

    auth = None
    if settings.weaviate_api_key:
        from weaviate.classes.init import Auth
        auth = Auth.api_key(settings.weaviate_api_key)

    client = weaviate.connect_to_custom(
        http_host=host,
        http_port=http_port,
        http_secure=parsed.scheme == "https",
        grpc_host=host,
        grpc_port=grpc_port,
        grpc_secure=parsed.scheme == "https",
        auth_credentials=auth,
        skip_init_checks=False,
    )
    log.info("connected to Weaviate at %s (grpc %d)", settings.weaviate_url, grpc_port)
    return client


@lru_cache(maxsize=1)
def get_store() -> WeaviateVectorStore:
    """Return the shared, multi-tenancy-enabled vector store (cached singleton).

    A single store object is reused for all users; isolation comes from the
    `tenant=` argument passed on each operation, NOT from separate store
    objects. `use_multi_tenancy=True` makes the library require a tenant on
    every read/write (and raise if one is missing - the safe failure mode).
    """
    return WeaviateVectorStore(
        client=get_weaviate_client(),
        index_name=settings.weaviate_index_name,
        text_key="text",
        embedding=get_embeddings(),
        use_multi_tenancy=True,
    )


def get_user_vectorstore(user_id: str | uuid.UUID) -> WeaviateVectorStore:
    """Back-compat shim: returns the shared MT store.

    NOTE: unlike the old Chroma version, the returned store is NOT scoped to the
    user by itself. Callers MUST pass tenant=tenant_for(user_id) on each
    operation. Prefer the add_/search_/delete_ helpers below which do this for
    you. Kept so existing imports don't break.
    """
    return get_store()


# --- Tenant lifecycle ------------------------------------------------------

def ensure_tenant(user_id: str | uuid.UUID) -> None:
    """Create the user's tenant if it doesn't exist yet.

    langchain-weaviate auto-creates a tenant on first write, but we expose this
    so the collection + tenant can be provisioned explicitly (e.g. on first
    document access) and so reads on a brand-new user don't error.
    """
    client = get_weaviate_client()
    _ensure_collection_exists(client)
    coll = client.collections.get(settings.weaviate_index_name)
    name = tenant_for(user_id)
    existing = coll.tenants.get()
    if name not in existing:
        from weaviate.classes.tenants import Tenant
        coll.tenants.create([Tenant(name=name)])
        log.info("created tenant %s", name)


def _ensure_collection_exists(client: weaviate.WeaviateClient) -> None:
    """Create the MT-enabled collection once, if absent."""
    if client.collections.exists(settings.weaviate_index_name):
        return
    from weaviate.classes.config import Configure
    client.collections.create(
        name=settings.weaviate_index_name,
        multi_tenancy_config=Configure.multi_tenancy(enabled=True),
    )
    log.info("created Weaviate collection %s (multi-tenancy on)", settings.weaviate_index_name)


def _tenant_exists(user_id: str | uuid.UUID) -> bool:
    """Return True iff the user's tenant currently exists in Weaviate."""
    try:
        client = get_weaviate_client()
        if not client.collections.exists(settings.weaviate_index_name):
            return False
        coll = client.collections.get(settings.weaviate_index_name)
        return tenant_for(user_id) in coll.tenants.get()
    except Exception:
        return False


def delete_user_collection(user_id: str | uuid.UUID) -> None:
    """Drop a user's tenant entirely. Used on account deletion / reindex wipe."""
    try:
        client = get_weaviate_client()
        if not client.collections.exists(settings.weaviate_index_name):
            return
        coll = client.collections.get(settings.weaviate_index_name)
        name = tenant_for(user_id)
        if name in coll.tenants.get():
            coll.tenants.remove([name])
            log.info("deleted tenant %s", name)
    except Exception as e:
        log.warning("failed to delete tenant for %s: %s", user_id, e)


def delete_user_docs_dir(user_id: str | uuid.UUID) -> None:
    """Remove a user's docs folder and all its files. Unchanged from Chroma."""
    import shutil
    path = docs_dir_for(user_id)
    if path.exists():
        shutil.rmtree(path)
        log.info("deleted docs dir for user %s", user_id)


def delete_user_workspace_dir(user_id: str | uuid.UUID) -> None:
    """Remove a user's legacy attachment workspace (data/repl_workspace/<hex>).

    Attachments are no longer copied there, but folders written by older
    versions may still exist and must not outlive the account.
    """
    import shutil
    if isinstance(user_id, str):
        user_id = uuid.UUID(user_id)
    path = settings.data_dir / "repl_workspace" / user_id.hex
    if path.exists():
        shutil.rmtree(path)
        log.info("deleted attachment workspace for user %s", user_id)


# --- Tenant-scoped data operations (the safe choke point) ------------------

def add_documents_for(user_id: str | uuid.UUID, chunks: list) -> list[str]:
    """Add chunks to the user's tenant. Auto-creates collection+tenant."""
    ensure_tenant(user_id)
    return get_store().add_documents(chunks, tenant=tenant_for(user_id))


def search_for(user_id: str | uuid.UUID, query: str, k: int):
    """Similarity search within the user's tenant only.

    Returns [] if the tenant doesn't exist yet (e.g. user hasn't uploaded
    anything, or a background job runs under the SYSTEM_USER_ID default).
    This is the correct semantic - no tenant = no docs = empty results -
    and prevents Weaviate from erroring on missing-tenant lookups.
    """
    if not _tenant_exists(user_id):
        return []
    return get_store().similarity_search_with_relevance_scores(
        query, k=k, tenant=tenant_for(user_id)
    )


def fetch_all_for(user_id: str | uuid.UUID, limit: int = 1000) -> list:
    """Fetch ALL chunks in the user's tenant as LangChain Documents.

    Unlike search_for (similarity search), this returns every object in the
    tenant - used by document_summarizer, which needs the whole document or
    corpus rather than the top-k for a query. Returns [] if the tenant doesn't
    exist (no uploads yet, or a background job under SYSTEM_USER_ID).

    `limit` caps how many objects we pull so a huge corpus can't blow up memory
    or the prompt; callers (the summarizer) truncate the combined text anyway.
    """
    from langchain_core.documents import Document

    try:
        if not _tenant_exists(user_id):
            return []
        client = get_weaviate_client()
        coll = client.collections.get(settings.weaviate_index_name)
        tenant_coll = coll.with_tenant(tenant_for(user_id))
        res = tenant_coll.query.fetch_objects(limit=limit)
        docs: list[Document] = []
        for obj in res.objects:
            props = obj.properties or {}
            text = props.get("text", "")
            meta = {k: v for k, v in props.items() if k != "text"}
            docs.append(Document(page_content=text, metadata=meta))
        return docs
    except Exception as e:
        log.debug("fetch_all_for failed: %s", e)
        return []


def count_for(user_id: str | uuid.UUID) -> int:
    """Number of objects (chunks) in the user's tenant. 0 if tenant absent."""
    try:
        if not _tenant_exists(user_id):
            return 0
        client = get_weaviate_client()
        coll = client.collections.get(settings.weaviate_index_name)
        tenant_coll = coll.with_tenant(tenant_for(user_id))
        return tenant_coll.aggregate.over_all(total_count=True).total_count
    except Exception as e:
        log.debug("count_for failed: %s", e)
        return 0


def delete_by_source_file(user_id: str | uuid.UUID, filename: str) -> int:
    """Delete all chunks whose source_file == filename, within the tenant."""
    from weaviate.classes.query import Filter

    if not _tenant_exists(user_id):
        return 0
    client = get_weaviate_client()
    coll = client.collections.get(settings.weaviate_index_name)
    tenant_coll = coll.with_tenant(tenant_for(user_id))
    # Count matches first (for the return value), then delete.
    res = tenant_coll.query.fetch_objects(
        filters=Filter.by_property("source_file").equal(filename),
        limit=10000,
    )
    n = len(res.objects)
    if n:
        tenant_coll.data.delete_many(
            where=Filter.by_property("source_file").equal(filename)
        )
        log.info("deleted %d chunks for %s (user=%s)", n, filename, user_id)
    return n


def count_by_source_file(user_id: str | uuid.UUID, filename: str) -> int:
    """Count chunks for a specific source file within the tenant."""
    from weaviate.classes.query import Filter

    try:
        if not _tenant_exists(user_id):
            return 0
        client = get_weaviate_client()
        coll = client.collections.get(settings.weaviate_index_name)
        tenant_coll = coll.with_tenant(tenant_for(user_id))
        res = tenant_coll.aggregate.over_all(
            total_count=True,
            filters=Filter.by_property("source_file").equal(filename),
        )
        return res.total_count
    except Exception as e:
        log.debug("count_by_source_file failed: %s", e)
        return 0
