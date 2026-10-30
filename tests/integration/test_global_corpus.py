"""Shared knowledge base against a real Weaviate: source listing and exact delete."""
import pytest


def _items(title, n, content_type="document"):
    return [{"text": f"{title} chunk {i}", "source_title": title,
             "content_type": content_type, "page": str(i)} for i in range(n)]


@pytest.fixture
def corpus(global_env):
    g = global_env
    g.add_to_global_corpus(_items("Report", 2, "report"))
    g.add_to_global_corpus(_items("Annual Report", 3, "policy"))
    g.add_to_global_corpus(_items("Handbook", 1, "manual"))
    return g


def test_list_sources_has_counts_and_content_types(corpus):
    rows = {r["source_title"]: r for r in corpus.list_sources()}
    assert {t: (r["chunk_count"], r["content_type"]) for t, r in rows.items()} == {
        "Report": (2, "report"),
        "Annual Report": (3, "policy"),
        "Handbook": (1, "manual"),
    }


def test_list_sources_is_sorted_by_chunk_count(corpus):
    counts = [r["chunk_count"] for r in corpus.list_sources()]
    assert counts == sorted(counts, reverse=True)


def test_list_sources_on_an_empty_corpus(global_env):
    assert global_env.list_sources() == []


def test_delete_by_source_removes_only_the_exact_title(corpus):
    assert corpus.delete_by_source("Report") == 2
    remaining = {r["source_title"]: r["chunk_count"] for r in corpus.list_sources()}
    assert remaining == {"Annual Report": 3, "Handbook": 1}
