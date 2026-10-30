"""Limits on what untrusted text can make the agent do (prompt-injection defence).

Documents, web pages and attachments are untrusted: they can contain text that
tries to steer the model ("ignore your instructions and search for ..."). The
one tool that sends data to a third party is `web_search`, so a poisoned
document's best move is to get private text into a search query. This module
makes that harder:

  * `web_query_problem` rejects a query that is unreasonably long or that
    copies a stretch of the user's private text (their indexed documents or an
    attachment) verbatim.
  * `neutralize_attachment_text` stops attachment text from closing its own
    delimiter block and writing outside it.

This is defence in depth, not a complete fix: a model can still be persuaded to
paraphrase or encode data into a short query, or to mislead the user in its
answer. The tools are read-only, `web_search` runs at most once per turn, and
the check below bounds what that one query can carry.
"""
import re

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

# Tools whose output is the user's own private text. The shared knowledge base
# is deliberately not listed: it is readable by every user.
PRIVATE_TOOLS = ("document_search", "document_summarizer")

ATTACHMENT_BEGIN = "--- BEGIN ATTACHMENT ---"
ATTACHMENT_END = "--- END ATTACHMENT ---"

MAX_WEB_QUERY_CHARS = 200
# A query that repeats this many characters of private text in a row is treated
# as copying it (about 6-8 words). Chinese, Japanese and Korean pack roughly a
# word into each character, so a shorter run counts there.
MIN_COPIED_CHARS = 40
MIN_COPIED_CHARS_CJK = 12

_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def _norm(text: str) -> str:
    return _NON_WORD.sub(" ", text.lower()).strip()


def neutralize_attachment_text(text: str) -> str:
    """Make the attachment delimiters inside `text` harmless.

    Without this, a file containing the end marker could "close" the attachment
    block and have what follows read as the user's own instructions.
    """
    return text.replace(ATTACHMENT_BEGIN, "[attachment marker removed]").replace(
        ATTACHMENT_END, "[attachment marker removed]"
    )


def clean_filename_label(name: str, max_chars: int = 100) -> str:
    """A filename safe to embed in a prompt line (no newlines or control chars)."""
    return _CONTROL.sub(" ", name).strip()[:max_chars] or "attached file"


def private_texts(messages: list[BaseMessage]) -> list[str]:
    """Private text currently in the conversation: outputs of the private
    search tools and attachment blocks (never the user's own question)."""
    texts: list[str] = []
    for m in messages:
        if isinstance(m, ToolMessage) and m.name in PRIVATE_TOOLS and isinstance(m.content, str):
            texts.append(m.content)
        elif isinstance(m, HumanMessage) and isinstance(m.content, str) and ATTACHMENT_BEGIN in m.content:
            start = m.content.index(ATTACHMENT_BEGIN) + len(ATTACHMENT_BEGIN)
            end = m.content.find(ATTACHMENT_END, start)
            texts.append(m.content[start:end if end != -1 else None])
    return texts


def web_query_problem(query: str, texts: list[str]) -> str | None:
    """Why this web_search query must not be sent, or None if it may go."""
    if len(query) > MAX_WEB_QUERY_CHARS:
        return (
            f"the query is longer than {MAX_WEB_QUERY_CHARS} characters; "
            f"use a short query of a few words"
        )
    q = _norm(query)
    cjk = len(_CJK.findall(q)) > len(q) / 2
    size = MIN_COPIED_CHARS_CJK if cjk else MIN_COPIED_CHARS
    if len(q) < size:
        return None
    windows = {q[i:i + size] for i in range(len(q) - size + 1)}
    for text in texts:
        haystack = _norm(text)
        if any(w in haystack for w in windows):
            return (
                "the query repeats text from the user's private documents or "
                "attachment; search the web with your own short wording instead"
            )
    return None
