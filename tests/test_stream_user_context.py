"""The streaming agent must give its tools the signed-in user.

StreamingResponse pumps a sync generator, and LangGraph runs tools on its own
worker threads. A user set once at the start of the generator did not reach
those threads, so the tools fell back to the shared system user and
document_search looked in an empty tenant ("No matching information found").
The non-streaming path was fine, which is why only the chat UI was affected.
"""
import uuid

import anyio
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from starlette.concurrency import iterate_in_threadpool

from app.agent import graph
from app.rag.user_context import SYSTEM_USER_ID, get_current_user

seen: list = []


@tool
def who_am_i(label: str) -> str:
    """Record which user the tool runs as."""
    seen.append(get_current_user())
    return label


class _ToolRunGraph:
    """An agent node followed by the real tools node, like the real agent graph.

    The tools run in a later step than the one that starts the stream, which is
    exactly where the user used to be lost.
    """

    def __init__(self):
        def agent(_state):
            calls = [{"name": "who_am_i", "args": {"label": n}, "id": n} for n in ("a", "b")]
            return {"messages": [AIMessage(content="", tool_calls=calls)]}

        g = StateGraph(graph.AgentState)
        g.add_node("agent", agent)
        g.add_node("tools", graph.DedupToolNode([who_am_i]))
        g.add_edge(START, "agent")
        g.add_edge("agent", "tools")
        g.add_edge("tools", END)
        self.compiled = g.compile()

    def stream(self, _input, config=None, stream_mode=None):
        return self.compiled.stream({"messages": []}, config=config, stream_mode=stream_mode)


def _run_like_starlette(user_id):
    async def run():
        events = graph.stream_agent("hi", "s1", user_id=user_id)
        return [e async for e in iterate_in_threadpool(events)]

    return anyio.run(run)


def _stub(monkeypatch):
    seen.clear()
    monkeypatch.setattr(graph, "get_graph", _ToolRunGraph)
    monkeypatch.setattr(graph, "maybe_generate_title", lambda *a: None)
    monkeypatch.setattr(graph.memory, "get", lambda *a, **k: [])
    monkeypatch.setattr(graph.memory, "append", lambda *a, **k: None)


def test_tools_run_as_the_signed_in_user_while_streaming(monkeypatch):
    _stub(monkeypatch)
    user_id = uuid.uuid4()

    events = _run_like_starlette(user_id)

    assert events[-1]["type"] == "done"
    assert seen, "the tool never ran"
    assert set(seen) == {user_id}


def test_the_user_does_not_leak_into_the_callers_context(monkeypatch):
    _stub(monkeypatch)

    _run_like_starlette(uuid.uuid4())

    assert get_current_user() == SYSTEM_USER_ID
