"""Ensemble degradation: failed candidates and an unusable judge (app/agent/ensemble.py)."""
import asyncio
from types import SimpleNamespace

import pytest

from app.agent import ensemble
from app.core.config import Settings, settings

JUDGE = "judge-model"


def _reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class FakeClient:
    """`behaviour` maps model name -> reply text, an exception, or "hang"."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, model, **kwargs):
        self.calls.append(model)
        b = self.behaviour[model]
        if b == "hang":
            await asyncio.sleep(5)
        if isinstance(b, Exception):
            raise b
        return b


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr(Settings, "ensemble_models_list", property(lambda s: ["a", "b", "c"]))
    monkeypatch.setattr(Settings, "active_judge_model", property(lambda s: JUDGE))
    monkeypatch.setattr(settings, "ensemble_timeout_sec", 1)

    def _run(behaviour):
        client = FakeClient(behaviour)
        monkeypatch.setattr(ensemble, "_build_client_for_active_provider", lambda: (client, "groq"))
        return asyncio.run(ensemble.run_ensemble_async("q")), client

    return _run


def test_judge_verdict_is_used_when_it_returns_json(run):
    judge = _reply('Sure! {"ranking": [{"model": "a", "rank": 1, "reason": "best"}], "verdict": "A"}')
    res, _ = run({"a": _reply("short"), "b": _reply("longer"), "c": _reply("x"), JUDGE: judge})
    assert res.verdict == "A"
    assert [(r.model, r.rank) for r in res.ranking] == [("a", 1)]


def test_failed_and_timed_out_candidates_are_reported_not_fatal(run):
    behaviour = {
        "a": _reply("fine"), "b": RuntimeError("rate limited"), "c": "hang",
        JUDGE: _reply('{"ranking": [], "verdict": "ok"}'),
    }
    res, _ = run(behaviour)
    errors = {c.model: c.error for c in res.candidates}
    assert errors["a"] is None
    assert "rate limited" in errors["b"]
    assert errors["c"].startswith("timeout")
    assert res.verdict == "ok"


@pytest.mark.parametrize(
    "judge",
    [_reply("not json at all"), _reply(None), _reply('{"ranking": []}'),
     RuntimeError("judge down"), "hang"],
)
def test_unusable_judge_falls_back_to_longest_answer(run, judge):
    res, _ = run({"a": _reply("mid answer"), "b": _reply("the longest answer"),
                  "c": RuntimeError("x"), JUDGE: judge})
    assert res.verdict == "the longest answer"
    assert {r.model for r in res.ranking} == {"a", "b"}  # failed candidate excluded
    assert all(r.reason == "judge unavailable" for r in res.ranking)


def test_all_candidates_failing_skips_the_judge(run):
    res, client = run({"a": RuntimeError("x"), "b": RuntimeError("y"), "c": _reply(""), JUDGE: _reply("{}")})
    assert JUDGE not in client.calls
    assert res.ranking == []
    assert "All candidate models failed" in res.verdict
