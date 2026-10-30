"""Tool: search the user's OWN indexed documents (personal corpus only).

Scoped strictly to the active user's tenant in CloudNestDocs. For the shared
admin-curated knowledge base, the agent has a separate tool
(knowledge_base_search). Keeping these two tools scope-distinct stops the
agent from oscillating between them on ambiguous questions.
"""
from langchain_core.tools import tool

from app.rag.chain import rag_answer_personal_only


@tool(response_format="content_and_artifact")
def document_search(question: str) -> tuple[str, list[dict]]:
    """Search the user's OWN indexed documents (personal uploads only).

    Use this for questions about files the user uploaded themselves. For
    admin-curated reference material (policies, manuals, FAQs, shared docs),
    use knowledge_base_search instead.

    Call this AT MOST ONCE per turn. If it returns no useful info, say so
    honestly - do not retry with reworded queries.

    Args:
        question: A natural-language question to search the personal documents for.

    Returns:
        An answer with bracketed source citations, or a no-answer message.
    """
    result = rag_answer_personal_only(question)
    if not result.sources:
        return "No matching information found in the user's personal documents.", []
    sources_str = ", ".join(s.source_file for s in result.sources)
    # The second value is an artifact: structured sources for the UI. It is not
    # shown to the model, and the graph reads it instead of searching again.
    return (
        f"{result.answer}\n\nSources: {sources_str}",
        [s.model_dump() for s in result.sources],
    )
