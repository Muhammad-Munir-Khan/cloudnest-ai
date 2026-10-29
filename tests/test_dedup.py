"""Tests for DedupToolNode: per-run dedup state, no sharing across runs."""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

from app.agent.graph import AgentState, DedupToolNode

CALLS: list[str] = []


@tool
def document_search(question: str) -> str:
    """Fake personal-document search that records each real execution."""
    CALLS.append(question)
    return f"private result for {question}"


def _call(question: str, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "document_search", "args": {"question": question}, "id": call_id}],
    )


def _tools_graph(node: DedupToolNode):
    """One-node graph so the node runs inside a LangGraph runtime, as in prod."""
    g = StateGraph(AgentState)
    g.add_node("tools", node)
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    return g.compile()


def _last_tool_message(state) -> ToolMessage:
    return [m for m in state["messages"] if isinstance(m, ToolMessage)][-1]


def setup_function():
    CALLS.clear()


def test_runs_do_not_share_cache():
    # One node instance shared by every run, as in production.
    graph = _tools_graph(DedupToolNode([document_search]))

    out_a = graph.invoke({"messages": [HumanMessage(content="q"), _call("same", "a1")]})
    assert out_a["tool_cache"]
    assert _last_tool_message(out_a).content == "private result for same"

    # Run B (fresh state) makes the identical call: it must execute for real,
    # not receive run A's cached output or a single-shot block.
    out_b = graph.invoke({"messages": [HumanMessage(content="q"), _call("same", "b1")]})
    assert CALLS == ["same", "same"]
    assert "already used" not in _last_tool_message(out_b).content


def test_repeat_within_run_is_served_from_cache():
    graph = _tools_graph(DedupToolNode([document_search]))
    first = graph.invoke({"messages": [_call("x", "c1")]})

    second = graph.invoke({
        "messages": [*first["messages"], _call("x", "c2")],
        "tool_cache": first["tool_cache"],
        "tools_ran": first["tools_ran"],
    })
    assert CALLS == ["x"]  # executed once
    msg = _last_tool_message(second)
    assert msg.tool_call_id == "c2"
    assert msg.content == "private result for x"


def test_single_shot_blocks_second_call_with_new_args():
    graph = _tools_graph(DedupToolNode([document_search]))
    first = graph.invoke({"messages": [_call("x", "c1")]})
    second = graph.invoke({
        "messages": [*first["messages"], _call("y", "c2")],
        "tool_cache": first["tool_cache"],
        "tools_ran": first["tools_ran"],
    })
    assert CALLS == ["x"]
    assert "already used this turn" in _last_tool_message(second).content


def test_state_flows_through_agent_loop_per_invocation():
    """In a full agent loop the cache persists across iterations of one run,
    and a second invocation of the same compiled graph starts clean."""
    script: list[AIMessage] = []

    def agent(state: AgentState):
        return {"messages": [script.pop(0)]}

    def route(state: AgentState):
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else END

    g = StateGraph(AgentState)
    g.add_node("agent", agent)
    g.add_node("tools", DedupToolNode([document_search]))
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    g.add_edge("tools", "agent")
    graph = g.compile()

    for run in ("r1", "r2"):
        script[:] = [_call("q", f"{run}-1"), _call("q", f"{run}-2"), AIMessage(content="done")]
        graph.invoke({"messages": [HumanMessage(content="hi")]})

    # Each run executed the tool exactly once (repeat served from cache),
    # and run 2 was not affected by run 1's cache.
    assert CALLS == ["q", "q"]
