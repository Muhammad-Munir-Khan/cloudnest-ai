"""Conversation memory — the last N message pairs for an active session.

Backed by Postgres. Each call fetches fresh from the database, which means:
  - Memory survives server restarts
  - Multiple uvicorn workers stay in sync
  - Cost: ~10ms per turn for a SELECT with LIMIT

The old in-memory dict-based memory is gone. If you need an in-process cache
later for performance, add it as a layer on top of this — don't replace this.
"""
import uuid

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agent import storage
from app.core.config import settings


class Memory:
    """Reads conversation history from Postgres on demand."""

    def get(
        self,
        session_id: str,
        user_id: str | uuid.UUID = storage.SYSTEM_USER_ID,
        limit: int | None = None,
    ) -> list[BaseMessage]:
        """Return the last N messages as LangChain BaseMessage objects.

        N defaults to 2 * memory_window (window pairs of user/assistant messages).
        """
        n = limit or (settings.memory_window * 2)
        rows = storage._run_sync(
            storage.alist_recent_messages(user_id, session_id, n)
        )
        return [self._to_langchain(r) for r in rows]

    def append(
        self,
        session_id: str,
        message: BaseMessage,
        user_id: str | uuid.UUID = storage.SYSTEM_USER_ID,
    ) -> None:
        """Persist a message. Auto-creates the session if needed."""
        role = self._role_for(message)
        storage.append_message(
            session_id=session_id,
            role=role,
            content=message.content,
            user_id=user_id,
        )

    def clear(
        self,
        session_id: str,
        user_id: str | uuid.UUID = storage.SYSTEM_USER_ID,
    ) -> None:
        """Delete the entire session."""
        storage.delete_session(session_id, user_id=user_id)

    @staticmethod
    def _role_for(message: BaseMessage) -> str:
        if isinstance(message, HumanMessage):
            return "user"
        if isinstance(message, AIMessage):
            return "assistant"
        return "system"

    @staticmethod
    def _to_langchain(row: dict) -> BaseMessage:
        if row["role"] == "user":
            return HumanMessage(content=row["content"])
        if row["role"] == "assistant":
            return AIMessage(content=row["content"])
        # System messages aren't expected in chat history but handle gracefully.
        return HumanMessage(content=row["content"])


memory = Memory()
