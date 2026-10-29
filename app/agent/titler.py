"""Generate a short title for a chat session from its first exchange."""
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_llm
from app.core.logging import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = (
    "You generate short titles for chat conversations. "
    "Given the user's first message and the assistant's first reply, "
    "produce a title of 3-6 words that captures the topic. "
    "Output ONLY the title — no quotes, no punctuation at the end, "
    "no prefixes like 'Title:'. Use Title Case."
)


def generate_title(user_message: str, assistant_reply: str, max_chars: int = 60) -> str | None:
    """Return a short title, or None if generation fails."""
    try:
        llm = get_llm()
        prompt = (
            f"User's first message:\n{user_message[:500]}\n\n"
            f"Assistant's first reply:\n{assistant_reply[:500]}\n\n"
            f"Title:"
        )
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        title = (response.content or "").strip()
        # Strip any wrapping quotes the model might add despite the instruction
        title = title.strip('"').strip("'").strip()
        # Take first line only
        title = title.split("\n")[0].strip()
        # Cap length
        title = title[:max_chars]
        return title or None
    except Exception as e:
        log.warning("title generation failed: %s", e)
        return None
