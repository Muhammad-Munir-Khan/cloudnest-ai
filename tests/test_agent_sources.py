"""Citations come from the search tools' own results, not a second search (PERF-01)."""
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from app.agent.graph import AgentState, DedupToolNode, _extract_sources
from app.core.schemas import QueryResponse, SourceInfo
from app.tools import document_search as doc_tool
from app.tools import knowledge_base as kb_tool


def _run_tools(tools, *calls):
    """Run tool calls through DedupToolNode inside a one-node graph (as in prod)."""
    g = StateGraph(AgentState)
    g.add_node("tools", DedupToolNode(tools))
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    ai = AIMessage(content="", tool_calls=[
        {"name": n, "args": {"question": q}, "id": f"c{i}"} for i, (n, q) in enumerate(calls)
    ])
    out = g.compile().invoke({"messages": [HumanMessage(content="hi"), ai]})
    return out["messages"]


def _personal_response(*files):
    return QueryResponse(
        answer="the answer",
        sources=[SourceInfo(source_file=f, page=1, snippet="s", score=0.9, origin="personal")
                 for f in files],
        latency_ms=1,
    )


def _no_second_search(monkeypatch):
    """Fail the test if anything searches again after the tools ran."""
    def boom(*a, **k):
        raise AssertionError("retrieval was re-run to build citations")
    monkeypatch.setattr("app.rag.retrieval.retrieve", boom)
    monkeypatch.setattr("app.rag.global_collection.global_search", boom)


def test_document_search_sources_come_from_the_tool_result(monkeypatch):
    monkeypatch.setattr(doc_tool, "rag_answer_personal_only", lambda q: _personal_response("a.pdf", "b.txt"))
    msgs = _run_tools([doc_tool.document_search], ("document_search", "q"))
    _no_second_search(monkeypatch)
    sources = _extract_sources(msgs)
    assert [s.source_file for s in sources] == ["a.pdf", "b.txt"]
    assert all(s.origin == "personal" for s in sources)
    tool_msg = [m for m in msgs if isinstance(m, ToolMessage)][0]
    assert "the answer" in tool_msg.content and "a.pdf, b.txt" in tool_msg.content  # model still sees text


def test_knowledge_base_sources_have_title_page_and_origin(monkeypatch):
    hit = Document(page_content="x" * 500,
                   metadata={"source_title": "Handbook", "page": "7", "content_type": "manual"})
    monkeypatch.setattr(kb_tool, "global_search", lambda q, k: [(hit, 0.83456)])
    msgs = _run_tools([kb_tool.knowledge_base_search], ("knowledge_base_search", "q"))
    _no_second_search(monkeypatch)
    (src,) = _extract_sources(msgs)
    assert (src.source_file, src.page, src.score, src.origin) == ("Handbook", 7, 0.835, "knowledge_base")
    assert len(src.snippet) == 240


def test_personal_sources_come_before_knowledge_base_sources(monkeypatch):
    hit = Document(page_content="kb", metadata={"source_title": "KB doc"})
    monkeypatch.setattr(doc_tool, "rag_answer_personal_only", lambda q: _personal_response("mine.pdf"))
    monkeypatch.setattr(kb_tool, "global_search", lambda q, k: [(hit, 0.5)])
    msgs = _run_tools([kb_tool.knowledge_base_search, doc_tool.document_search],
                      ("knowledge_base_search", "q"), ("document_search", "q"))
    assert [s.source_file for s in _extract_sources(msgs)] == ["mine.pdf", "KB doc"]


def test_no_results_means_no_sources(monkeypatch):
    monkeypatch.setattr(doc_tool, "rag_answer_personal_only", lambda q: _personal_response())
    monkeypatch.setattr(kb_tool, "global_search", lambda q, k: [])
    msgs = _run_tools([doc_tool.document_search, kb_tool.knowledge_base_search],
                      ("document_search", "q"), ("knowledge_base_search", "q"))
    assert _extract_sources(msgs) == []


def test_failed_search_gives_no_sources(monkeypatch):
    def fail(q, k):
        raise RuntimeError("weaviate down")
    monkeypatch.setattr(kb_tool, "global_search", fail)
    msgs = _run_tools([kb_tool.knowledge_base_search], ("knowledge_base_search", "q"))
    assert _extract_sources(msgs) == []
    assert "failed" in [m for m in msgs if isinstance(m, ToolMessage)][0].content


def test_blocked_repeat_does_not_hide_the_first_result(monkeypatch):
    """In a later step of the same turn, a second document_search is suppressed
    (no artifact); the first call's sources must still be reported."""
    calls = []
    monkeypatch.setattr(doc_tool, "rag_answer_personal_only",
                        lambda q: calls.append(q) or _personal_response("first.pdf"))
    g = StateGraph(AgentState)
    g.add_node("tools", DedupToolNode([doc_tool.document_search]))
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    graph = g.compile()

    def call(q, cid):
        return AIMessage(content="", tool_calls=[
            {"name": "document_search", "args": {"question": q}, "id": cid}])

    step1 = graph.invoke({"messages": [HumanMessage(content="hi"), call("one", "c1")]})
    step2 = graph.invoke({
        "messages": step1["messages"] + [call("two", "c2")],
        "tool_cache": step1["tool_cache"],
        "tools_ran": step1["tools_ran"],
    })
    assert calls == ["one"]  # the repeat never ran
    assert "already used" in [m for m in step2["messages"] if isinstance(m, ToolMessage)][-1].content
    assert [s.source_file for s in _extract_sources(step2["messages"])] == ["first.pdf"]


def test_other_tools_and_malformed_artifacts_are_ignored():
    msgs = [
        ToolMessage(content="1035", tool_call_id="a", name="calculator", artifact=[{"source_file": "x"}]),
        ToolMessage(content="r", tool_call_id="b", name="document_search", artifact=[{"nonsense": 1}]),
        ToolMessage(content="r", tool_call_id="c", name="document_search", artifact=None),
    ]
    assert _extract_sources(msgs) == []
