"""Tool: summarize an indexed document (or the whole corpus) at varying depth."""
from typing import Literal

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from app.core.llm import get_llm
from app.rag.collections import fetch_all_for
from app.rag.user_context import get_current_user

SUMMARY_PROMPT = """You are a precise document summarizer. Summarize the text below.

Guidelines:
- Length: {length_instruction}
- Stick to facts present in the text. Do not speculate.
- Preserve specific numbers, names, and dates.
- Use neutral, professional language.

Text to summarize:
{content}

Summary:"""

LENGTH_PRESETS = {
    "short": "1-2 sentences capturing only the main point.",
    "medium": "1 paragraph (~5 sentences) covering the key points.",
    "long": "2-3 paragraphs covering main points and important details.",
}


def _gather_chunks(filename: str | None) -> list[Document]:
    """Pull all chunks from the CURRENT user's tenant, optionally filtered.

    Uses the tenant-scoped fetch_all_for helper in collections.py (the single
    choke point for per-user Weaviate access) rather than touching the store
    internals directly.
    """
    user_id = get_current_user()
    docs = fetch_all_for(user_id)
    if filename:
        target = filename.strip().lower()
        docs = [
            d for d in docs
            if d.metadata.get("source_file", "").lower() == target
        ]
    return docs


@tool
def document_summarizer(
    filename: str | None = None,
    length: Literal["short", "medium", "long"] = "medium",
) -> str:
    """Summarize an indexed document, or all indexed documents.

    Use this when the user asks for an overview, summary, or "what's in" a
    file or the corpus. For specific facts use document_search instead.

    Args:
        filename: The source filename to summarize (e.g. "test.txt").
            If None, summarizes the entire indexed corpus.
        length: "short" (1-2 sentences), "medium" (1 paragraph),
            or "long" (2-3 paragraphs). Default: medium.

    Returns:
        The summary text, prefixed with the source name.
    """
    docs = _gather_chunks(filename)
    if not docs:
        if filename:
            return (
                f"No indexed content found for {filename!r}. "
                f"Make sure the file is uploaded and ingested."
            )
        return "No documents are currently indexed for this user."

    text_parts = [d.page_content for d in docs]
    combined = "\n\n".join(text_parts)
    cap = 6000
    if len(combined) > cap:
        combined = combined[:cap] + "\n\n[...truncated for length...]"

    prompt = ChatPromptTemplate.from_template(SUMMARY_PROMPT)
    chain = prompt | get_llm()
    response = chain.invoke({
        "length_instruction": LENGTH_PRESETS[length],
        "content": combined,
    })

    label = filename or "all indexed documents"
    return f"Summary of {label}:\n\n{response.content}"
