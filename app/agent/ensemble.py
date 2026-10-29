"""Multi-LLM ensemble: ask several models in parallel, then have a judge
model rank the responses and pick a winner.

Provider-aware: when LLM_PROVIDER=groq, fans out across Groq models via the
native Groq SDK. When LLM_PROVIDER=openrouter, fans out across OpenRouter
models via the OpenAI SDK pointed at OpenRouter's base URL (both providers
speak the same Chat Completions protocol, so the per-call code is identical).

This module bypasses the LangGraph agent entirely — no tools, no memory.

Robustness note: free-tier / overloaded providers occasionally return a
response whose `choices` is None or empty (rather than raising), which used to
surface as the cryptic "'NoneType' object is not subscriptable". _content_of()
guards that and yields a clean, informative error instead.
"""
import asyncio
import json
import re
import time

from pydantic import BaseModel

from app.core.config import settings
from app.core.language import language_directive
from app.core.logging import get_logger

log = get_logger(__name__)

CANDIDATE_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the user's question directly and "
    "accurately. Be concise but complete. If you don't know, say so."
)

JUDGE_SYSTEM_PROMPT = """You are an expert evaluator comparing AI model responses.

Given a user question and N candidate answers from different models, you must:
1. Rank them from best (#1) to worst.
2. Briefly explain your reasoning (1-2 sentences).
3. Synthesize the best possible final answer, drawing from the strongest candidate(s).

Score on: factual accuracy, completeness, clarity, and direct relevance to the question.
Penalize: hallucinations, padding/fluff, evasiveness, off-topic content.

Output ONLY valid JSON in this exact shape:
{
  "ranking": [
    {"model": "model-name", "rank": 1, "reason": "brief reason"},
    {"model": "model-name", "rank": 2, "reason": "brief reason"},
    {"model": "model-name", "rank": 3, "reason": "brief reason"}
  ],
  "verdict": "the synthesized best answer to the user's question"
}

No prose outside the JSON. No markdown code fences."""


class CandidateResponse(BaseModel):
    model: str
    answer: str
    latency_ms: int
    error: str | None = None


class JudgeRanking(BaseModel):
    model: str
    rank: int
    reason: str


class EnsembleResponse(BaseModel):
    question: str
    candidates: list[CandidateResponse]
    ranking: list[JudgeRanking]
    verdict: str
    judge_model: str
    total_latency_ms: int


def _content_of(response) -> str:
    """Safely extract message content from a chat-completions response.

    Free-tier / overloaded providers sometimes return an object whose
    `choices` is None or empty instead of raising. Accessing
    response.choices[0] then throws "'NoneType' object is not subscriptable",
    which is opaque. This guards each step and raises a clear RuntimeError that
    the callers turn into a readable candidate/judge error.
    """
    choices = getattr(response, "choices", None)
    if not choices:
        # Surface any provider-supplied error detail if present.
        err = getattr(response, "error", None)
        detail = f" (provider error: {err})" if err else ""
        raise RuntimeError(f"model returned no choices{detail}")
    first = choices[0]
    message = getattr(first, "message", None)
    if message is None:
        raise RuntimeError("model returned a choice with no message")
    return message.content or ""


# ---------------------------------------------------------------------------
# Per-call helpers (identical across providers — both speak the OpenAI proto)
# ---------------------------------------------------------------------------

async def _ask_one(
    client, model: str, question: str, lang_directive: str
) -> CandidateResponse:
    """Call a single model. Returns a CandidateResponse with error on failure."""
    t0 = time.time()
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": CANDIDATE_SYSTEM_PROMPT + lang_directive},
                    {"role": "user", "content": question},
                ],
                temperature=0.3,
                max_tokens=settings.ensemble_max_tokens,
            ),
            timeout=settings.ensemble_timeout_sec,
        )
        answer = _content_of(response)
        return CandidateResponse(
            model=model,
            answer=answer.strip(),
            latency_ms=int((time.time() - t0) * 1000),
        )
    except asyncio.TimeoutError:
        return CandidateResponse(
            model=model,
            answer="",
            latency_ms=int((time.time() - t0) * 1000),
            error=f"timeout after {settings.ensemble_timeout_sec}s",
        )
    except Exception as e:
        return CandidateResponse(
            model=model,
            answer="",
            latency_ms=int((time.time() - t0) * 1000),
            error=str(e)[:200],
        )


async def _judge(
    client,
    judge_model: str,
    question: str,
    candidates: list[CandidateResponse],
    lang_directive: str,
) -> dict:
    """Call the judge model with all candidates. Returns parsed JSON or fallback."""
    valid = [c for c in candidates if c.answer and not c.error]
    if not valid:
        return {
            "ranking": [],
            "verdict": "All candidate models failed to respond. Please try again.",
        }

    candidates_text = "\n\n".join(
        f"=== Candidate {i + 1}: {c.model} ===\n{c.answer}" for i, c in enumerate(valid)
    )

    user_prompt = (
        f"USER QUESTION:\n{question}\n\n"
        f"CANDIDATE ANSWERS:\n{candidates_text}\n\n"
        f"Rank these {len(valid)} candidates and synthesize the best final answer. "
        f"Output JSON only, no markdown fences."
    )

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=judge_model,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT + lang_directive},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=1200,
                response_format={"type": "json_object"},
            ),
            timeout=settings.ensemble_timeout_sec,
        )
        raw = _content_of(response) or "{}"
        # Strip any stray markdown fences, then pull out the JSON object. Using a
        # regex to locate the outermost {...} is more robust than lstrip tricks
        # (which could mangle content) when a model wraps JSON in prose/fences.
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError("no JSON object found in judge response")
        return json.loads(match.group(0))
    except asyncio.TimeoutError:
        log.warning("judge failed: timeout after %ss", settings.ensemble_timeout_sec)
        return _judge_fallback(valid)
    except Exception as e:
        log.warning("judge failed: %s", e)
        return _judge_fallback(valid)


def _judge_fallback(valid: list[CandidateResponse]) -> dict:
    """When the judge can't run, pick the longest valid answer and mark the
    ranking as judge-unavailable so the UI can show candidates honestly."""
    best = max(valid, key=lambda c: len(c.answer))
    return {
        "ranking": [
            {"model": c.model, "rank": i + 1, "reason": "judge unavailable"}
            for i, c in enumerate(valid)
        ],
        "verdict": best.answer,
    }


# ---------------------------------------------------------------------------
# Provider-specific client construction
# ---------------------------------------------------------------------------

def _build_client_for_active_provider():
    """Return an async OpenAI-compatible client + the active provider name.

    Both Groq's native SDK and OpenAI's SDK expose the same `client.chat.
    completions.create(...)` API surface, so downstream code doesn't care
    which one it gets.
    """
    provider = settings.llm_provider.lower()

    if provider == "groq":
        if not settings.groq_api_key:
            raise RuntimeError(
                "Multi-LLM mode requires GROQ_API_KEY in .env when LLM_PROVIDER=groq."
            )
        from groq import AsyncGroq
        return AsyncGroq(api_key=settings.groq_api_key), provider

    if provider == "openrouter":
        if not settings.openrouter_api_key:
            raise RuntimeError(
                "Multi-LLM mode requires OPENROUTER_API_KEY in .env when "
                "LLM_PROVIDER=openrouter."
            )
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai package not installed. Run: pip install openai"
            ) from e

        default_headers = {}
        if settings.openrouter_site_url:
            default_headers["HTTP-Referer"] = settings.openrouter_site_url
        if settings.openrouter_app_name:
            default_headers["X-Title"] = settings.openrouter_app_name

        return (
            AsyncOpenAI(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
                default_headers=default_headers or None,
            ),
            provider,
        )

    raise RuntimeError(
        f"Multi-LLM mode does not support provider {provider!r}. "
        f"Use 'groq' or 'openrouter'."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_ensemble_async(question: str, language: str = "en") -> EnsembleResponse:
    """Fire candidates in parallel, then run the judge on the results.

    Models and judge are selected from settings based on the active provider:
      - LLM_PROVIDER=groq        → GROQ_ENSEMBLE_MODELS + GROQ_ENSEMBLE_JUDGE_MODEL
      - LLM_PROVIDER=openrouter  → OPENROUTER_ENSEMBLE_MODELS + OPENROUTER_ENSEMBLE_JUDGE_MODEL
    """
    client, provider = _build_client_for_active_provider()

    candidate_models = settings.ensemble_models_list
    judge_model = settings.active_judge_model

    if not candidate_models:
        raise RuntimeError(
            f"Ensemble model list for provider {provider!r} is empty. "
            f"Set the appropriate env var in .env."
        )
    if len(candidate_models) < 2:
        raise RuntimeError(
            f"Ensemble needs at least 2 models, got {len(candidate_models)} "
            f"for provider {provider!r}."
        )

    lang_directive = language_directive(language)
    t0 = time.time()

    log.info(
        "ensemble (%s): %d candidates: %s | judge: %s | language: %s",
        provider,
        len(candidate_models),
        candidate_models,
        judge_model,
        language,
    )

    candidates = await asyncio.gather(
        *[_ask_one(client, m, question, lang_directive) for m in candidate_models]
    )

    judgment = await _judge(client, judge_model, question, candidates, lang_directive)

    rankings = [
        JudgeRanking(
            model=r.get("model", "?"),
            rank=int(r.get("rank", 0)),
            reason=r.get("reason", ""),
        )
        for r in (judgment.get("ranking") or [])
    ]
    verdict = judgment.get("verdict") or "(no verdict)"

    return EnsembleResponse(
        question=question,
        candidates=candidates,
        ranking=rankings,
        verdict=verdict,
        judge_model=judge_model,
        total_latency_ms=int((time.time() - t0) * 1000),
    )


def run_ensemble(question: str, language: str = "en") -> EnsembleResponse:
    """Sync wrapper for FastAPI. Spawns its own loop."""
    return asyncio.run(run_ensemble_async(question, language))
