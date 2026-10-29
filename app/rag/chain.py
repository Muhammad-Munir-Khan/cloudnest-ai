"""Single-shot RAG chain: retrieve top-k chunks then answer with citations.

Two flavors:

  rag_answer(question, ...)
      Retrieves from BOTH the user's personal documents AND the shared global
      knowledge base. Used by the /rag/query endpoint (RAG mode in chat) so
      users get answers from everything available to them.

  rag_answer_personal_only(question, ...)
      Retrieves from ONLY the user's personal documents. Used by the agent's
      document_search tool so its scope matches its name and docstring. Keeps
      document_search semantically distinct from knowledge_base_search and
      prevents the agent from getting confused about which retrieval tool to
      pick (a real cause of tool-spam loops).

Each SourceInfo carries an `origin` field ("personal" or "knowledge_base")
so the UI can render a small badge distinguishing the two.
"""
import time

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from app.core.language import language_directive
from app.core.llm import get_llm
from app.core.schemas import QueryResponse, SourceInfo
from app.rag.retrieval import retrieve, retrieve_merged

SYSTEM_PROMPT = """You are a precise assistant that answers strictly from the provided context.

The context below contains chunks from two possible sources:
- The user's own indexed documents.
- A shared knowledge base curated by administrators.

Rules:
- Use ONLY the information in the context below.
- If the context does not contain the answer, reply: "I don't know based on the provided documents."
- After each factual claim, cite the source like [filename].
- Be concise.

Context:
{context}
"""


def _source_label(doc: Document) -> str:
    """Best human-readable label for a chunk.

    Personal docs:        metadata["source_file"]
    Global KB chunks:     metadata["source_title"]  (set by admin upload)
    Falls back to "unknown" if neither is present.
    """
    md = doc.metadata or {}
    return md.get("source_file") or md.get("source_title") or "unknown"


def format_context(docs: list[Document]) -> str:
    parts = []
    for i, d in enumerate(docs, 1):
        src = _source_label(d)
        page = (d.metadata or {}).get("page", "?")
        origin = (d.metadata or {}).get("origin", "personal")
        origin_label = "knowledge base" if origin == "knowledge_base" else "your documents"
        parts.append(f"[{i}] {src} (p.{page}, {origin_label})\n{d.page_content}")
    return "\n\n".join(parts)


def _docs_to_sources(pairs: list[tuple[Document, float]]) -> list[SourceInfo]:
    """Convert retrieval pairs into SourceInfo, threading `origin` through."""
    sources: list[SourceInfo] = []
    for d, s in pairs:
        md = d.metadata or {}
        origin = md.get("origin", "personal")
        # `page` may be a non-int string ("?", "") from some loaders; coerce
        # carefully so SourceInfo (page: int | None) stays happy.
        raw_page = md.get("page")
        try:
            page_val = int(raw_page) if raw_page not in (None, "", "?") else None
        except (TypeError, ValueError):
            page_val = None
        sources.append(
            SourceInfo(
                source_file=_source_label(d),
                page=page_val,
                snippet=d.page_content[:240],
                score=round(s, 3) if s is not None else None,
                origin=origin if origin in ("personal", "knowledge_base") else "personal",
            )
        )
    return sources


def _answer_from_pairs(
    question: str,
    pairs: list[tuple[Document, float]],
    language: str,
    empty_msg: str,
    t0: float,
) -> QueryResponse:
    """Shared body for both rag_answer flavors.

    Same prompt, same LLM, same response shape - only difference between
    the two callers is which retrieval the `pairs` came from.
    """
    docs = [p[0] for p in pairs]
    if not docs:
        return QueryResponse(
            answer=empty_msg,
            sources=[],
            latency_ms=int((time.time() - t0) * 1000),
        )

    context = format_context(docs)
    system_with_lang = SYSTEM_PROMPT + language_directive(language)

    prompt = ChatPromptTemplate.from_messages(
        [("system", system_with_lang), ("user", "{question}")]
    )
    chain = prompt | get_llm()
    response = chain.invoke({"context": context, "question": question})

    return QueryResponse(
        answer=response.content,
        sources=_docs_to_sources(pairs),
        latency_ms=int((time.time() - t0) * 1000),
    )


def rag_answer(
    question: str,
    top_k: int | None = None,
    language: str = "en",
) -> QueryResponse:
    """Answer using BOTH personal docs AND the shared knowledge base.

    Used by /rag/query (chat RAG mode). Sources are tagged by origin so the
    UI can distinguish personal vs KB.
    """
    t0 = time.time()
    pairs = retrieve_merged(question, k=top_k)
    return _answer_from_pairs(
        question=question,
        pairs=pairs,
        language=language,
        empty_msg=(
            "I don't have anything indexed to answer from yet. "
            "Upload a document, or ask an admin to add content to the knowledge base."
        ),
        t0=t0,
    )


def rag_answer_personal_only(
    question: str,
    top_k: int | None = None,
    language: str = "en",
) -> QueryResponse:
    """Answer using ONLY the user's personal indexed documents.

    Used by the document_search agent tool so the tool's behavior actually
    matches its docstring ("the user's OWN indexed documents"). Keeping the
    scope tight prevents the agent from confusing document_search with
    knowledge_base_search and thrashing between them.
    """
    t0 = time.time()
    pairs = retrieve(question, k=top_k)
    return _answer_from_pairs(
        question=question,
        pairs=pairs,
        language=language,
        empty_msg="No matching information found in your indexed documents.",
        t0=t0,
    )
