"""Tool: search the shared knowledge base (admin-curated, global).

This is the agent-facing counterpart to /admin/corpus/search. It searches the
SHARED knowledge base that admins ingest into (the global corpus), NOT the
user's personal documents. Use document_search for the user's own files.

Design note (intentional, mirrors web_search NOT document_search):
  document_search calls rag_answer() internally - which runs another LLM
  pass to synthesize an answer from chunks before returning. That makes sense
  for personal docs because the synthesis cost is small and the answer is
  the product.

  For the KB tool we deliberately DO NOT run an inner LLM. We just return
  the top chunks (text + brief citation header) and let the agent's main
  LLM synthesize. This is faster, cheaper, and parallels how web_search
  hands back raw results for the agent to reason over.
"""
from langchain_core.tools import tool

from app.core.schemas import SourceInfo
from app.rag.global_collection import global_search

# Tunable: how many KB chunks the agent sees per call.
# Small enough not to bloat the prompt; large enough to give real coverage.
_TOP_K = 5

# Truncate each chunk so a single bad/huge object can't crowd the context.
_SNIPPET_CHARS = 600


def _source_info(doc, score) -> SourceInfo:
    """Citation for one knowledge-base hit (what the UI shows)."""
    md = doc.metadata or {}
    # KB uses source_title (set by admin upload); page may be a string
    # (it comes from PDF loaders as a str sometimes).
    title = md.get("source_title") or md.get("book_title") or "unknown"
    raw_page = md.get("page")
    try:
        page = int(raw_page) if raw_page not in (None, "", "?") else None
    except (TypeError, ValueError):
        page = None
    return SourceInfo(
        source_file=title,
        page=page,
        snippet=doc.page_content[:240],
        score=round(float(score), 3) if score is not None else None,
        origin="knowledge_base",
    )


@tool(response_format="content_and_artifact")
def knowledge_base_search(question: str) -> tuple[str, list[dict]]:
    """Search the shared knowledge base (admin-curated, available to everyone).

    Use this when the question is about content that an administrator would
    have added to the shared knowledge base - reference material, policies,
    manuals, curated documents - rather than the user's own uploaded files.

    Args:
        question: A natural-language question to search the knowledge base for.

    Returns:
        Top matching chunks with citations, or a no-result message.
    """
    try:
        results = global_search(question, k=_TOP_K)
    except Exception as e:
        return f"Knowledge base search failed: {e}", []

    if not results:
        return "No matching information found in the shared knowledge base.", []

    lines: list[str] = []
    for i, (doc, score) in enumerate(results, start=1):
        md = doc.metadata or {}
        title = md.get("source_title") or md.get("book_title") or "(untitled)"
        ctype = md.get("content_type") or "document"
        author = md.get("author")
        page = md.get("page")

        header_parts = [f"[{i}] {title}", f"type={ctype}"]
        if author:
            header_parts.append(f"by {author}")
        if page:
            header_parts.append(f"p.{page}")
        if score is not None:
            header_parts.append(f"score={float(score):.2f}")

        text = (doc.page_content or "").strip()
        if len(text) > _SNIPPET_CHARS:
            text = text[:_SNIPPET_CHARS].rstrip() + "..."

        lines.append(" | ".join(header_parts))
        lines.append(text)
        lines.append("")  # blank line between hits

    # Second value is an artifact (structured sources for the UI); the graph
    # reads it instead of searching again.
    return "\n".join(lines).rstrip(), [_source_info(d, s).model_dump() for d, s in results]
