# Architecture

An overview of CloudNest.ai: what each part does and why. The README covers setup and the full endpoint list; this file explains how the pieces fit.

## Goals

1. **Multi-tenant.** Every user's chats, documents and vectors are isolated from every other user's.
2. **Swappable LLM provider.** One setting (`LLM_PROVIDER`: `groq`, `openrouter` or `ollama`) routes the agent, RAG, ensemble and vision paths.
3. **Production-shaped.** Auth, rate limiting, audit logging, migrations, health probes, CI and a hardened compose overlay.
4. **Honest.** Answers come from the user's documents, the shared knowledge base, the web or a tool, with citations; limits are written down in the README.

## System

```
Next.js 15 frontend  <--HTTP + SSE-->  FastAPI backend (LangGraph agent)
                                          |-- LLM provider (Groq / OpenRouter / Ollama)
                                          |-- Weaviate: per-user tenants + shared GlobalKnowledgeBase
                                          |-- PostgreSQL: users, roles, sessions, messages, OAuth accounts
                                          |-- Redis: rate limiting and login/email throttling
                                          '-- optional: Langfuse (traces), Sentry (errors)
```

## Backend layers (`app/`)

- **`core/`** Cross-cutting concerns. `config.py` is the only place settings are read (`pydantic-settings`; 52 required fields, `.env.example` is the complete template). `auth.py` wires fastapi-users (JWT in an httpOnly cookie or a bearer header, OAuth for Google and GitHub, password policy, per-account lockout) and the force-logout freshness check. `roles.py`/`admin_deps.py` implement the three roles (`user`, `corpus_admin`, `super_admin`); `role` is the only source of admin rights. `rate_limit.py` (Redis, client IP from `X-Forwarded-For` only via `TRUSTED_PROXIES`), `security_headers.py`, `body_limit.py`, `audit.py` (structured audit events), `email.py`, `observability.py`.
- **`rag/`** `collections.py` is the single choke point for per-user Weaviate access: one multi-tenant collection, tenant `user_<hex>` per user, and the tenant is passed on every operation. `ingestion.py` loads PDF, TXT, MD and DOCX, chunks them and indexes into the user's tenant (re-uploading a file replaces its chunks). `global_collection.py` is the shared, admin-curated knowledge base. `retrieval.py` and `chain.py` merge personal and knowledge-base hits for RAG answers. `extraction.py` extracts text from attachments and falls back to the provider's vision model for scanned PDFs and images. `user_context.py` holds the current user in a contextvar so tools never take a `user_id` argument.
- **`tools/`** Ten LangChain tools registered in `registry.py`: `document_search`, `knowledge_base_search`, `document_summarizer`, `web_search`, `calculator` (AST evaluator, bounded exponentiation), `json_parser`, `datetime_tool`, `unit_converter`, `currency_converter`, `weather`.
- **`agent/`** `graph.py` is the LangGraph ReAct loop (`agent` node with tools bound, `tools` node) with a dedup tool node that blocks repeated single-shot retrievals within one run; run-scoped state, so concurrent users never share a cache. `memory.py` and `storage.py` keep session history in Postgres (on a background event loop); `titler.py` names chats; `ensemble.py` fans a question out to several models of the active provider and has a judge rank and synthesize them, falling back to the longest valid answer if the judge fails.
- **`voice/`** `stt.py` (faster-whisper) and `tts.py` (Edge neural voices, or Piper offline).
- **`api/`** Routers for agent, RAG, voice, attachments and admin, plus shared upload limits and error helpers (clients see a generic message and a reference id; details go to the log).
- **`models/` + `alembic/`** SQLAlchemy models and migrations; the entrypoint runs `alembic upgrade head` before starting uvicorn.

The embedding model (`BAAI/bge-m3`, multilingual, 1024 dimensions) is pre-warmed at startup. Changing it changes the vector size, so existing collections must be re-created and documents re-indexed.

## Key flows

- **Question about the user's documents:** the agent decides to call `document_search`, which embeds the question, searches the user's tenant and returns text with sources; the agent answers with citations. `/rag/query` runs the same retrieval directly, merging half of the results from the personal tenant and half from the knowledge base.
- **Streaming:** `/agent/stream` emits Server-Sent Events: token deltas, tool start and end events, then a final event with sources and the session id. The frontend falls back to `/agent/chat` if streaming fails.
- **Force-logout and suspension:** every token carries `iat`. Every authenticated route runs the freshness check against `users.jwt_invalidated_at`, so an admin's force-logout (or suspension, which sets both `is_active=false` and the cutoff in one update) takes effect on the next request.
- **Delete a user (admin):** one Postgres transaction removes messages, sessions, OAuth rows and the user; then the Weaviate tenant and on-disk files are removed best-effort.

## Deployment

`docker/docker-compose.yml` runs postgres, redis, weaviate, api and frontend (plus `ollama` and `ollama-pull` with `--profile ollama`). `docker/docker-compose.prod.yml` is an overlay that closes the data-service ports, requires passwords and API keys, and adds Caddy for automatic HTTPS. Health probes: `/health/live` (process up) and `/health/ready` (Postgres required; Redis and Weaviate reported). CI (GitHub Actions) runs the tests, lint, frontend build, image builds and blocking dependency scans. No hosting platform has been chosen yet.

## Trade-offs accepted

- **The agent gets retrieval as tools, not a prompt prefix,** so the model decides per turn whether to search documents, the knowledge base, the web, or nothing. Two separately scoped retrieval tools avoid the recursion loops an overlapping pair caused.
- **Shared multi-tenant collection** instead of a collection per user: cleaner operations, with isolation depending on always passing the tenant; an integration test against a real Weaviate guards this.
- **Rate limiting fails open** when Redis is unreachable (configurable), so a cache outage does not take the app down.
- **RAG and ensemble turns are not saved to chat history yet** (agent turns are); reloading a session shows only the saved turns.
- **Prompt injection is not defended against:** a malicious document or web page could try to steer the agent.
- **CPU-only Ollama is slow;** Groq is the recommended primary path.

## Where to extend

| Want to... | Touch... |
|---|---|
| Add a tool | `app/tools/your_tool.py`, register it in `registry.py`, mention it in the system prompt in `agent/graph.py` |
| Add a setting | a field in `Settings` (`core/config.py`), `.env.example`, and the README table |
| Add a route | a router in `app/api/`, mounted in `main.py` with a rate limit and `current_active_user` (or `require_role`) |
| Change the schema | edit `app/models/`, then `alembic revision --autogenerate -m "..."` |
| Swap the vector database | `app/rag/collections.py` and `global_collection.py` (all Weaviate access is there) |
| Add an LLM provider | `core/llm.py` and the provider properties on `Settings` |
