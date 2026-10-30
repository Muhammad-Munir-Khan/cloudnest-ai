# CloudNest.ai

> Your own AI workspace. Your data. Your rules.

A self-hostable, multi-tenant conversational AI platform built end-to-end. Combines per-user retrieval-augmented generation, a shared admin-curated knowledge base, a 10-tool agent loop, multi-LLM consensus mode, voice in/out, vision, true multilingual retrieval across 100+ languages, strict per-turn response-language control, a real admin panel, and a streaming Next.js frontend. Switches between Groq, OpenRouter, and Ollama through one config line. Deploys with one Docker command.

> **Author:** [Munir Khan](https://www.linkedin.com/in/munirkhan-ai/) · [LinkedIn](https://www.linkedin.com/in/munirkhan-ai/)
>
> **Stack:** FastAPI · LangGraph · LangChain · PostgreSQL · Weaviate · BGE-M3 embeddings · faster-whisper · Edge TTS · Next.js 15 · Tailwind · fastapi-users · Langfuse · Docker
>
> **Three swappable LLM providers.** Groq for raw speed, OpenRouter for access to ~100 commercial models (Claude, GPT-4, Gemini), or Ollama for fully local inference. One `.env` line picks the active backend — and the same line also routes the vision and ensemble paths. See the [provider support matrix](#provider-support) for tested behavior on each.

---

## What it does

- **Per-user document Q&A with real citations.** Every user gets a private Weaviate tenant. Upload PDFs, TXT, MD, or DOCX through the UI (drop images and scanned PDFs into the chat for vision OCR) — every answer surfaces source filenames, page numbers, and similarity scores so you can verify rather than trust.
- **Shared knowledge base curated by admins.** Upload company policies, product manuals, FAQs once. Every user queries them through the same chat. Citations show which source came from personal documents vs the shared knowledge base, rendered with distinct visual badges.
- **Real admin panel.** Three-tier role system (user / corpus_admin / super_admin). Manage users, suspend accounts (with optional reason emailed to the user), reset passwords, force-logout active sessions instantly. Curate the shared knowledge base with file uploads and hybrid-search preview. Live system stats.
- **10-tool agent loop.** A LangGraph ReAct agent decides per turn whether to search the user's documents, search the shared knowledge base, search the web, do math, parse JSON, work with dates, convert units or currency, fetch weather, or just answer.
- **Multilingual retrieval (100+ languages).** Powered by `BAAI/bge-m3`, a state-of-the-art multilingual embedding model. Upload a manual in English, query it in Urdu — cross-lingual retrieval works because the embeddings share semantic space across languages.
- **Strict response-language control (37 languages).** A language selector sets the response language independently of retrieval. Switch from English to Japanese mid-conversation and every subsequent answer — chat, RAG, and the ensemble verdict — responds in the selected language, overriding the language of earlier turns. This is distinct from the cross-lingual *retrieval* above: one controls what language the model *answers in*, the other lets it *find* relevant chunks regardless of language.
- **Multi-LLM consensus mode.** Toggle on to fan a single query out to **3 different models in parallel**. A 4th model judges the responses, ranks them with reasoning, and synthesizes a final verdict. Works on either Groq or OpenRouter — picks the active provider automatically, and honors the selected response language in both candidates and verdict.
- **Chats that survive a reload.** Agent, RAG and ensemble turns are all saved to the session, together with their sources, tool calls and latency, so citations are still there when you reopen a conversation. Re-uploading a document replaces its old chunks instead of duplicating them.
- **Streaming with live agent trace.** SSE-based token streaming. Tool calls appear in a vertical timeline as they execute (`knowledge_base_search` → `calculator` → `currency_converter`), each transitioning from `running` to `done` in real time.
- **Production-grade authentication & isolation.** JWT + httpOnly cookies (XSS-resistant). Bearer token also supported for CLI/API. OAuth via Google and GitHub. Postgres-backed user accounts. Per-user sessions, messages, documents, and Weaviate tenants. Two users on the same backend never see each other's data — enforced at the database, vector store, API, and agent-context layers.
- **Global force-logout.** When an admin force-logs out a user, every active session dies on the next request — not just admin pages. Implemented via JWT iat-cutoff checks on every authenticated endpoint.
- **Account suspension with email notifications.** Block flow auto-force-logs-out the user, sends a templated "account suspended" email with optional admin-provided reason. Unblock fires a restoration email. Suspended users attempting to log in with the correct password see a clear "account suspended" message (wrong-password attempts still get a generic error — no enumeration leak).
- **Security hardening.** Redis-backed rate limiting (brute-force protection on login, abuse caps on chat/RAG/voice), strict security headers (CSP, HSTS, nosniff, frame-deny) on every response, magic-byte upload validation, and structured audit logging of every security-relevant event. Optional Sentry error tracking and opt-in email verification. See [Security & hardening](#security--hardening).
- **Voice in / voice out.** faster-whisper for STT, Microsoft Edge neural voices for TTS. One-tap mic button. Matched native voices for 37 languages, with text normalization (markdown stripping, CJK/full-width punctuation handling) so non-Latin scripts synthesize cleanly.
- **Vision for images and scanned PDFs.** When text extraction falls short, a vision model reads the image directly — provider-aware: Llama-4 Scout 17B on Groq, Llama-3.2-11B-Vision on OpenRouter, or a local `llama3.2-vision` on Ollama. The vision model follows the active provider automatically; webp/gif inputs are normalized to PNG so every provider accepts them. No manual workflow.
- **Built-in observability.** Langfuse hooks wired into the agent loop. Every run captures tool calls, latencies, token usage, costs. Filter by user, replay tool trees for any failed answer.
- **Provider abstraction.** Groq, OpenRouter, or Ollama. Switch with `LLM_PROVIDER=...` in `.env`. Same agent loop, same tools, same UX — and the same switch repoints the vision and ensemble paths. The platform is built against a provider interface, not vendor lock-in.
- **Docker-native.** Single `docker compose up` brings the full stack online: API, Postgres, Redis, Weaviate, frontend (Ollama is optional: `--profile ollama`). Production-quality entrypoints with migrations, healthchecks, and embedded volumes.
- **Light/dark theme.** Branded cyan/teal gradient. CSS-variable architecture, no flash on page load. Theme toggle in both the landing page and the chat sidebar, synced through one hook.

---

## Provider support

One `.env` line (`LLM_PROVIDER`) routes the entire app — agent, RAG, ensemble, and vision — through the chosen backend. The same code paths run on all three; what differs is raw speed and, on free tiers, throughput. The table below reflects **tested** behavior, not aspiration:

| Capability | Groq | OpenRouter | Ollama (CPU-only) |
|---|---|---|---|
| Chat + agent (tools) | Fast, reliable | Works; slower on free tier (low-priority queue + auto-retries) | Works; slow on CPU |
| RAG + citations | Fast | Works | Works; slow |
| Response-language switching | Reliable | Reliable | Works (weaker models drift more) |
| Multi-LLM ensemble | Full, fast | Works; free-tier candidates/judge may queue or time out | Not recommended (too slow) |
| Vision OCR | Reliable (Llama-4 Scout) | Works when not throttled; intermittent on free tier | Proven but impractical on CPU |
| Tool-call loop protection | Rarely needed | Rarely needed | Dedup guard prevents weak-model loops |

**Groq is the recommended demo/primary path** — the entire feature set runs fast. **OpenRouter** unlocks ~100 commercial models and works end to end; on the free tier, ensemble and vision are intermittent because free requests hit a low-priority upstream queue, and a small credit removes that. **Ollama** gives fully local, no-API-key inference; it's solid for chat on modest hardware, but the multi-step agent and vision OCR are slow on CPU-only machines. A tool-call de-duplication guard keeps weak local models from spiraling into repeated identical tool calls.

---

## Security & hardening

Security controls applied across the stack. Everything below is **live in the running app** unless explicitly marked production-only.

- **Rate limiting (Redis-backed).** Per-endpoint limits keyed by client IP (`X-Forwarded-For` honoured only from `TRUSTED_PROXIES`): auth 10/min, registration 5/min, password reset and email verification 5/min, OAuth 20/min, `/users` 60/min, RAG 60/min, agent 120/min, admin 120/min, voice 30/min, attachments 30/min. On top of that, each account locks after 10 failed logins in 15 minutes (even for the correct password), and each address receives at most 3 reset or verification emails per hour. Fails open if Redis is briefly unavailable (`RATE_LIMIT_FAIL_OPEN=false` to fail closed), so a cache blip never takes the app down.
- **Security headers on every response.** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security`, and a strict `Content-Security-Policy` (relaxed only on the Swagger/redoc paths so the API explorer still renders).
- **CORS locked to known origins.** Explicit origin allowlist with credentials, tightened methods and headers — no wildcard origins.
- **Upload hardening.** Size caps (413 over 20MB for attachments, 25MB for knowledge-base files, 10MB for personal documents, plus a 30MB request-body ceiling for everything), extension allowlist, and magic-byte signature checks so a file can't lie about its type — a spoofed `.pdf` or a mislabeled image is rejected before parsing, not after.
- **Audit logging.** Every security-relevant event — login success/failure/blocked, registration, email verification, password reset, and admin actions (role change, suspend/unblock, force-logout, KB upload/delete) — emits a structured JSON line on a dedicated `audit` logger, ready to ship to a SIEM. Captures who did it and what it affected.
- **Error tracking (Sentry).** Optional; enabled only when a valid `SENTRY_DSN` is set, and guarded so a blank or malformed DSN can never crash startup. PII is not sent.
- **Email verification.** Verification-email plumbing wired through fastapi-users; enforcement is opt-in via `REQUIRE_EMAIL_VERIFICATION` (off by default so dev and existing accounts aren't disrupted). OAuth signups are verified automatically.
- **Secrets.** In development, secrets come from `.env`. In production they can be mounted as files (Docker / Kubernetes secrets at `/run/secrets/<field_name>`); pydantic-settings reads them automatically, with environment variables still taking precedence — so the same code is convenient in dev and safe in prod.
- **TLS — production overlay.** A Caddy reverse-proxy overlay (`docker/docker-compose.prod.yml` + `docker/Caddyfile`) terminates HTTPS with automatic Let's Encrypt certificates and stops the app/frontend from publishing ports directly. Development is unaffected.
- **Dependency scanning (CI).** Dependabot plus a GitHub Actions workflow running `pip-audit`, `npm audit` (high and above), and Trivy (high/critical) on every push, weekly, and on pull requests. They fail the build; the few advisories that cannot be fixed yet are listed with reasons in `.pip-audit-ignore` and `.trivyignore`.
- **Global force-logout & account suspension.** As described under the [admin panel](#admin-panel) — every authenticated endpoint enforces the JWT-freshness check.

---

## Architecture

```
+--------------------------+          +--------------------------+
|   Next.js 15 frontend    |   HTTP   |    FastAPI backend       |
|   (Tailwind + SSE)       | <------> |  (LangGraph + agents)    |
+--------------------------+          +--------------------------+
                                                  |
   +---------------+----------------+--------------+--------------+
   v               v                v                             v
+----------+ +-----------+ +-----------------+         +-------------------+
|   LLM    | |  Tools    | |  RAG pipeline   |         |  Admin panel      |
| provider | | registry  | |  Weaviate +     |         |  user mgmt, KB    |
| Groq /   | | (10       | |  BGE-M3         |         |  curation, role   |
| Open     | | tools)    | |  per-user       |         |  enforcement      |
| Router / | +-----------+ |  tenant +       |         +-------------------+
| Ollama   |       |       |  shared KB      |
+----------+       v       +-----------------+
            +-----------------+        +----------------+
            |  Voice & vision |        |    Langfuse    |
            |  Whisper + Edge |        |  observability |
            |  vision: per-   |        +----------------+
            |  provider model |
            +-----------------+

+----------------------------------------------------------------+
|                       PostgreSQL                                |
|  users · roles · sessions · messages · OAuth accounts          |
|  jwt_invalidated_at · alembic migrations                       |
+----------------------------------------------------------------+
```

**Per-user RAG path:**
`question + user_id (from contextvar) -> BGE-M3 embed -> Weaviate hybrid search in user tenant -> format with sources -> LLM -> answer + citations`

**Shared knowledge base path:**
`question -> BGE-M3 embed -> Weaviate hybrid (BM25 + vector) on GlobalKnowledgeBase collection -> chunks tagged with origin="knowledge_base" -> formatted into agent context with admin-curated metadata (book_title, author, page)`

**Merged retrieval (chat RAG mode):**
`question -> retrieve_merged() -> half of top-k from personal corpus + half from KB -> tagged with origin -> LLM answers with citations; UI badges personal vs KB sources distinctly`

**Agent path (multi-turn, streaming):**
`message + session history + user_id -> LangGraph 'agent' node -> LLM with bound tools -> if tool calls, route to 'tools' node (with dedup guard) -> loop until plain answer -> persist to Postgres -> emit SSE events as it runs`

**Multi-LLM ensemble path:**
`question -> asyncio.gather across N models on active provider -> judge model receives all candidates -> ranks them with JSON output -> synthesizes final verdict (in the selected response language)`

**Vision OCR path:**
`image/scanned PDF -> normalize to PNG -> route to active provider's vision model (active_vision_model) -> extracted text returned to the agent inline; the agent answers from that text directly rather than re-searching the corpus`

The agent is given retrieval as **two distinct tools** (`document_search` for personal docs, `knowledge_base_search` for the shared KB), not as a prompt prefix. The LLM decides whether documents are relevant for a given turn — much better than blindly retrieving on every message — and which corpus to query.

Per-user isolation is enforced through a Python `contextvar` set in the agent entry point. Every tool that touches user data (`document_search`, `document_summarizer`) reads `get_current_user()` and scopes its work accordingly. The pattern is small, auditable, and impossible to forget at the route layer. The shared knowledge base bypasses the tenant filter intentionally because it's a deliberate cross-user shared resource.

**Force-logout enforcement:** Every JWT carries an `iat` (issued-at) claim. The auth dependency (`current_active_user`) runs a freshness check against `users.jwt_invalidated_at` on every request. When an admin force-logs out a user, that column is set to `now()` — every JWT issued before that moment is rejected with 401. The check applies globally, not just to admin routes.

---

## Tools

The agent has 10 tools registered. It picks per turn based on the user's intent:

| Tool                    | What it does                                                       |
|-------------------------|--------------------------------------------------------------------|
| `document_search`       | Semantic + BM25 hybrid search over the current user's personal documents (Weaviate per-user tenant) |
| `knowledge_base_search` | Hybrid search over the shared admin-curated knowledge base         |
| `document_summarizer`   | Summarize a whole file or the user's entire personal corpus        |
| `web_search`            | DuckDuckGo (no API key needed)                                     |
| `calculator`            | Safe AST-based math (no `eval`), handles thousands-comma numbers   |
| `json_parser`           | Parse JSON and extract values via dotted path                      |
| `datetime_tool`         | Date math and timezone-aware queries                               |
| `unit_converter`        | Physical unit conversions using `pint`                             |
| `currency_converter`    | Live ECB exchange rates via Frankfurter API                        |
| `weather`               | Current + 3-day forecast (Open-Meteo)                              |

Tool selection turned out to be a system-prompt problem more than a model problem — most "wrong tool" issues went away after rewriting tool descriptions to emphasize *when* to use each one. A separate class of bug — recursion loops on compound multi-part questions — was traced via Langfuse to semantic overlap between `document_search` and `knowledge_base_search`; the fix was making the two tools genuinely scope-distinct and adding explicit "call each retrieval tool at most once per turn" guidance to the system prompt, backed by a runtime de-duplication guard in the tools node (identical repeat calls return the cached result; a second single-shot retrieval call is blocked with a nudge to answer from what's already gathered). The guard matters most on weak local models, which otherwise loop.

A related fix on the attachment path: when a file is dropped into the composer, its extracted text is injected inline into the turn. The agent used to call `document_summarizer` on the *filename* (searching the index, which doesn't contain the freshly attached file) instead of reading the text in front of it. Tightening both the system prompt and the inline framing — "this text IS the file's content, answer from it directly, do not call document tools for it" — fixed it.

> **Note on `python_repl` and `csv_reader`:** Both are in the repo but currently unregistered. Small open-source models (gpt-oss-20B, Llama 3.1 8B) hallucinate filenames and forget to `print()` results, making chained CSV-analysis flows unreliable. Phase 5 will re-enable them with a persistent Jupyter-style kernel and a larger tool-calling model. See the roadmap.

---

## Admin panel

A real user-management surface, not a settings page. Surfaced at `/admin` for users with `super_admin` or `corpus_admin` roles.

**Three-tier role system:**
- `user` — default for new signups. Can use chat, RAG, voice, and query the shared knowledge base.
- `corpus_admin` — can also manage the shared knowledge base (upload, delete, preview-search).
- `super_admin` — all of the above, plus user management (list, change role, suspend/unblock, edit display name, send password reset, force-logout, delete).

**User management capabilities:**
- **List users** with role, active status, verification status, creation date
- **Change role** (with self-protection: super_admins cannot demote themselves)
- **Suspend / unblock** an account. Suspend is atomic: `is_active=false` AND `jwt_invalidated_at=now()` in one transaction, killing any live session on the user's next request. Optional reason field included in the email.
- **Email notifications** on suspend and unblock. Suspended users attempting to log in with the correct password see a specific "account suspended" message; wrong-password attempts still get the generic error (no enumeration leak).
- **Force-logout** kills every active session for a user. Invalidates all JWTs issued before `now()`.
- **Send password reset** triggers the standard fastapi-users password reset flow.
- **Edit display name**.

**Knowledge base management capabilities:**
- **Upload documents** (.pdf, .txt, .md, .docx, up to 25MB) — chunked + embedded into the shared `GlobalKnowledgeBase` Weaviate collection. Uploading a file whose source title (default: the file name) already exists replaces that source's chunks instead of duplicating them.
- **Structured ingest** via JSON for fine control over per-chunk metadata.
- **List sources** grouped by source title with chunk counts.
- **Delete sources** by exact title match.
- **Preview hybrid search** with adjustable BM25/vector blend (alpha 0.0–1.0).

---

## Project structure

```
cloudnest/
├── app/                         # FastAPI backend
│   ├── core/                    # config · secrets · logging · LLM provider · auth · audit · email · DB · roles · admin_deps · language · security_headers · rate_limit · body_limit · oauth_email · observability
│   ├── rag/
│   │   ├── ingestion.py         # per-user document indexing
│   │   ├── retrieval.py         # contextvar-scoped retrieval + retrieve_merged (personal + KB)
│   │   ├── chain.py             # RAG answer chains (merged + personal-only)
│   │   ├── collections.py       # Weaviate client + per-user tenant management
│   │   ├── global_collection.py # GlobalKnowledgeBase (shared corpus) operations
│   │   ├── embeddings.py        # BGE-M3 singleton (lru_cache)
│   │   ├── extraction.py        # PDF/image text extraction + provider-aware vision OCR
│   │   └── user_context.py      # contextvar holding the active user UUID
│   ├── agent/
│   │   ├── graph.py             # LangGraph ReAct loop (run + stream + dedup tool node + citations from tool results)
│   │   ├── guard.py             # prompt-injection limits: web_search egress check, attachment delimiters
│   │   ├── ensemble.py          # Multi-LLM parallel execution + judge
│   │   ├── memory.py            # Session-scoped conversation buffer
│   │   ├── storage.py           # Postgres-backed sessions & messages
│   │   ├── turns.py             # saves RAG and ensemble turns with their metadata
│   │   └── titler.py            # LLM-based automatic chat naming
│   ├── tools/                   # 10 tool implementations
│   ├── voice/                   # STT (Whisper) + TTS (Edge / Piper)
│   ├── api/                     # FastAPI route modules (rag, agent, voice, attachments, admin) + shared error and upload helpers
│   ├── models/                  # SQLAlchemy models (user, oauth_account, chat session, chat message)
│   └── main.py                  # FastAPI entry point with lifespan pre-warm + exception handlers
│
├── frontend/                    # Next.js 15 app
│   ├── app/
│   │   ├── page.tsx             # Landing page
│   │   ├── chat/page.tsx        # Main chat UI
│   │   ├── login/page.tsx       # Login (cookie auth, surfaces suspended-account message)
│   │   ├── signup/page.tsx
│   │   ├── admin/               # Admin panel (users, corpus management, stats)
│   │   └── layout.tsx
│   ├── components/              # UI components (Sidebar, Composer, ChatMessage, SourcesPanel with KB badges, etc.)
│   └── lib/                     # API client, types, theme hook, auth helpers
│
├── docker/                      # Docker-compose stack + Dockerfiles + entrypoints
│   ├── docker-compose.yml       # full stack: postgres, redis, weaviate, api, frontend (+ ollama with --profile ollama)
│   ├── docker-compose.prod.yml  # production overlay: Caddy auto-HTTPS, no public app ports
│   ├── Caddyfile                # reverse proxy + automatic TLS (production)
│   ├── Dockerfile-backend
│   ├── Dockerfile-frontend
│   └── entrypoint.sh            # runs alembic upgrade head, then uvicorn on $PORT (default 8000)
│
├── scripts/                     # smoke_test.py (authenticated end-to-end check of a running stack)
├── tests/                       # pytest suite; tests/integration needs a running Weaviate
├── evals/                       # Ragas RAG evaluation harness
├── .github/                     # Dependabot config + CI (tests, lint, builds) and security-scan workflows
├── .pip-audit-ignore            # accepted security-scan exceptions, each with a reason (also .trivyignore)
│
├── alembic/                     # Database migrations (role, jwt_invalidated_at, created_at, chat message meta, ...)
├── data/                        # used by local-dev path only; ignored in Docker
├── requirements.txt             # exact pins (CPU torch is installed first, see Dockerfile-backend)
├── requirements-dev.txt         # pytest + ruff (includes requirements.txt)
├── .env.example
└── README.md
```

---

## Quick start (Docker — recommended)

The whole stack runs in Docker. This is the verified deployment path.

### Prerequisites
- Docker Desktop (or Docker Engine + Compose v2)
- 16GB RAM recommended (BGE-M3 model + Weaviate + Postgres + frontend)
- Either a free [Groq API key](https://console.groq.com/keys) or an [OpenRouter key](https://openrouter.ai/keys). Ollama is optional and runs inside the Docker stack when started with `--profile ollama`.

### 1. Clone + configure

```bash
git clone https://github.com/Muhammad-Munir-Khan/cloudnest-ai
cd cloudnest-ai
cp .env.example .env
```

Edit `.env` with at minimum:

```env
# Pick one provider
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your_key_here

# Strong secret for production (32+ chars random)
JWT_SECRET=your_strong_jwt_secret_here

# For password reset / account suspension emails (optional in dev)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=your_email@gmail.com

# Embeddings
EMBEDDING_MODEL=BAAI/bge-m3
```

> All env var names are uppercase (e.g. `GROQ_CHAT_MODEL`, `OPENROUTER_VISION_MODEL`). See the [Configuration](#configuration) table and `.env.example` for the full set. `LLM_PROVIDER` must be lowercase (`groq` / `openrouter` / `ollama`).

### 2. Bring up the stack

```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml logs -f
```

First boot downloads BGE-M3 (~2.2GB) — visible in the api logs as `pre-warming embedding model: BAAI/bge-m3`. Subsequent boots are fast (model cached in the container volume).

Containers brought up:
- `cloudnest-postgres` — Postgres 16 with user/session schema
- `cloudnest-redis` — Redis, backs request rate limiting
- `cloudnest-weaviate` — vector store, multi-tenant per-user
- `cloudnest-api` — FastAPI backend, runs Alembic migrations on entrypoint
- `cloudnest-frontend` — Next.js 15 frontend
- `cloudnest-ollama` + `cloudnest-ollama-pull` — local LLM provider, started only with `--profile ollama` (needed only if `LLM_PROVIDER=ollama`)

### 3. Open the app

http://localhost:3000

Create an account, log in, start uploading documents and chatting.

### 4. Promote yourself to super_admin

By default new signups get `role=user`. To get into the admin panel, set your role manually once:

```bash
docker exec -it cloudnest-postgres psql -U genai -d genai -c "UPDATE users SET role='super_admin', is_superuser=true WHERE email='you@example.com';"
```

Now reload — you'll see "Switch to Admin Panel" in the sidebar.

---

## Quick start (local dev — alternative)

If you'd rather run the backend and frontend directly (faster iteration on code, useful for development):

### Prerequisites
- Python 3.11
- Node.js 20+
- Docker (just for Postgres, Redis and Weaviate)

### Steps

```bash
# 1. Bring up only the data services in Docker, keep api/frontend native
docker compose -f docker/docker-compose.yml up -d postgres weaviate redis

# 2. Backend
python -m venv .venv
.\.venv\Scripts\activate          # Windows
# source .venv/bin/activate       # macOS / Linux
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.13.0   # CPU wheel first, as the Dockerfile does
pip install -r requirements-dev.txt   # runtime deps + pytest + ruff
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. Frontend (in a separate terminal)
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** (not `127.0.0.1` — cookie auth is scoped to `localhost` in dev).

---

## Demo questions to try

1. **Personal RAG with citations:** Upload a document, ask *"What does this document say about X?"* → returns the answer with source file + page + similarity score, with a "personal" badge on the source.
2. **Knowledge base retrieval:** As an admin, upload a company policy or manual to the KB. As any user, ask about it → answer cites the KB source with a distinct badge.
3. **Cross-lingual retrieval (BGE-M3):** Upload an English document, ask the question in Urdu or Arabic → retrieval still hits because BGE-M3 embeddings share semantic space across languages.
4. **Strict language switching:** Set the language selector to Japanese and say *"hi"* → こんにちは. Switch back to English and say *"hi"* again → the reply switches to English, even though the previous turn was Japanese. Ask the same question across several languages — each answer (and any citation) comes back in the selected language.
5. **Multi-step tool chain:** *"What is 87,500 × 24, then convert to EUR?"* → triggers `calculator` → `currency_converter`.
6. **Multi-LLM consensus:** Toggle multi-LLM mode, ask a judgment question → 3 models answer in parallel, judge ranks them, synthesized verdict appears (in your selected language).
7. **Vision OCR:** Drag in a screenshot or scanned invoice and ask *"what's in this document?"* → the active provider's vision model extracts the text and the agent answers from it directly.
8. **Voice round-trip:** Tap the mic, say *"What's the weather in Karachi?"*, hear the answer spoken back in your selected language.
9. **Admin: account suspension flow:** As super_admin, suspend a user with a reason → user is force-logged-out instantly, receives an email, sees the suspended message on next login attempt with correct password.
10. **Multi-tenant isolation:** Sign up as a second user — none of your first account's chats, documents, or RAG answers leak across.

---

## Configuration

Every tunable lives in `.env`. Env var names are uppercase; `LLM_PROVIDER` takes a lowercase value. Start from `cp .env.example .env`: 52 of the 70 settings have no built-in default and must be present, and the "Default" column below shows the values in that template (only the runtime flags `REDIS_URL`, `COOKIE_SECURE`, `REQUIRE_EMAIL_VERIFICATION`, `SENTRY_DSN`, `ENVIRONMENT` and `SENTRY_TRACES_SAMPLE_RATE` have real built-in defaults). Highlights:

| Variable                            | Default                            | Description                                                |
|-------------------------------------|------------------------------------|------------------------------------------------------------|
| `LLM_PROVIDER`                      | `groq`                             | Backend: `groq`, `openrouter`, or `ollama` (lowercase)     |
| `GROQ_CHAT_MODEL`                   | `openai/gpt-oss-20b`               | Main agent model when using Groq                           |
| `OPENROUTER_CHAT_MODEL`             | `meta-llama/llama-3.3-70b-instruct`| Main agent model when using OpenRouter                     |
| `OLLAMA_CHAT_MODEL`                 | `llama3.2:3b`                      | Main agent model when using Ollama                         |
| `GROQ_VISION_MODEL`                 | `meta-llama/llama-4-scout-17b-16e-instruct` | Vision model for OCR when using Groq              |
| `OPENROUTER_VISION_MODEL`           | `meta-llama/llama-3.2-11b-vision-instruct`  | Vision model for OCR when using OpenRouter        |
| `OLLAMA_VISION_MODEL`               | `llama3.2-vision`                  | Vision model for OCR when using Ollama (must be pulled)    |
| `EMBEDDING_MODEL`                   | `BAAI/bge-m3`                      | Embedding model. **Note:** changing this requires wiping existing Weaviate collections (dimension mismatch). |
| `GROQ_ENSEMBLE_MODELS`              | 3 Groq models                      | Comma-separated candidate list for ensemble (Groq path)    |
| `OPENROUTER_ENSEMBLE_MODELS`        | 3 OpenRouter models                | Comma-separated candidate list for ensemble (OpenRouter)   |
| `GROQ_ENSEMBLE_JUDGE_MODEL`         | `openai/gpt-oss-120b`              | Judge model on Groq                                        |
| `OPENROUTER_ENSEMBLE_JUDGE_MODEL`   | `openai/gpt-oss-120b:free`         | Judge model on OpenRouter                                  |
| `ENSEMBLE_MAX_TOKENS`               | `2000`                             | Max tokens per ensemble candidate / judge call             |
| `ENSEMBLE_TIMEOUT_SEC`              | `30`                               | Per-call timeout for ensemble candidates and judge         |
| `DATABASE_URL`                      | local Postgres                     | SQLAlchemy async DSN                                       |
| `JWT_SECRET`                        | dev placeholder                    | **Change for production.** Secret for signing JWTs.        |
| `JWT_LIFETIME_SECONDS`              | `604800`                           | Token lifetime (default 7 days)                            |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` | empty                      | Email delivery for password reset + account suspension     |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET`| empty                              | Optional Google OAuth                                       |
| `GITHUB_OAUTH_CLIENT_ID` / `_SECRET`| empty                              | Optional GitHub OAuth                                       |
| `LANGFUSE_PUBLIC_KEY` / `_SECRET_KEY` | empty                            | Optional observability backend                              |
| `CHUNK_SIZE / OVERLAP / TOP_K`      | `800 / 100 / 4`                    | RAG retrieval configuration                                |
| `WHISPER_MODEL`                     | `base`                             | STT model size: `tiny`, `base`, `small`, `medium`          |
| `TTS_BACKEND`                       | `edge`                             | Voice engine: `edge` (neural online) or `piper` (offline)  |
| `MAX_AGENT_ITERATIONS`              | `8`                                | Maximum tool-call loop iterations (recursion limit derived from this) |
| `MEMORY_WINDOW`                     | `10`                               | Past message pairs kept in agent context                   |
| `REDIS_URL`                         | `redis://redis:6379/0`             | Redis connection for request rate limiting                 |
| `COOKIE_SECURE`                     | `false`                            | Set `true` in production (HTTPS) so the auth cookie is sent only over secure connections |
| `REQUIRE_EMAIL_VERIFICATION`        | `false`                            | Set `true` to require a verified email before login (needs working SMTP) |
| `SENTRY_DSN`                        | empty                              | Sentry error-tracking DSN; empty or non-URL disables it    |
| `ENVIRONMENT`                       | `development`                      | Environment tag (used by Sentry and the production overlay)|
| `SENTRY_TRACES_SAMPLE_RATE`         | `0.1`                              | Fraction of requests traced when Sentry is enabled         |

See `.env.example` for the full reference with comments.

---

## API reference

The full API surface, grouped by area. Interactive docs with request/response schemas live at **http://localhost:8000/docs** (Swagger UI) and **http://localhost:8000/redoc**.

Most authenticated endpoints enforce the JWT-freshness check, so a force-logout immediately invalidates active sessions. Browser clients authenticate via the httpOnly cookie set by `/auth/cookie/login`; CLI tools and scripts use `Authorization: Bearer <token>` headers from `/auth/jwt/login`. Same JWT under the hood, two transport mechanisms.

### Auth (`/auth/*`)

User authentication via fastapi-users — dual JWT/cookie transport, password reset, email verification, and OAuth.

| Method | Path                            | Purpose                                                  |
|--------|---------------------------------|----------------------------------------------------------|
| POST   | `/auth/jwt/login`               | Login, response carries `{access_token, token_type}` (for API/curl/mobile) |
| POST   | `/auth/jwt/logout`              | Logout (no-op server-side; JWT is stateless)             |
| POST   | `/auth/cookie/login`            | Login, sets httpOnly `genai_auth` cookie (for browser)   |
| POST   | `/auth/cookie/logout`           | Logout, clears the cookie                                |
| POST   | `/auth/register`                | Register a new account with email + password             |
| POST   | `/auth/forgot-password`         | Send password reset email (fires `password_reset_email` template) |
| POST   | `/auth/reset-password`          | Complete password reset with token from email; fires `password_changed_email` notification |
| POST   | `/auth/request-verify-token`    | Send email verification token to a user                  |
| POST   | `/auth/verify`                  | Verify a user's email with the token from the verification email |
| GET    | `/auth/google/authorize`        | Begin Google OAuth flow — returns the authorization URL the browser should visit |
| GET    | `/auth/google/callback`         | OAuth callback: exchanges code, gets/creates/links the user, sets cookie, redirects to frontend |
| GET    | `/auth/github/authorize`        | Begin GitHub OAuth flow                                  |
| GET    | `/auth/github/callback`         | OAuth callback (same flow as Google)                     |

**Security notes:**
- Suspended accounts (set via admin panel) attempting to log in with the **correct password** receive a `403` with "account suspended" message. Wrong-password attempts still return generic `400` bad credentials — no enumeration leak.
- OAuth callbacks check suspension status. Blocked OAuth users redirect to `/login?error=...` instead of getting logged in.
- The custom JWT strategy adds an `iat` claim to every token so force-logout (via `users.jwt_invalidated_at`) can invalidate sessions atomically.

### Users (`/users/*`)

Own-profile management from fastapi-users' router. Only `/users/me` is mounted; the built-in `/users/{id}` routes are not (they authorized on `is_superuser` instead of role), so `role` is the only source of admin rights and user management lives under `/admin/users/*`.

| Method | Path                            | Purpose                                                  |
|--------|---------------------------------|----------------------------------------------------------|
| GET    | `/users/me`                     | Current user info (id, email, role, display_name, ...)   |
| PATCH  | `/users/me`                     | Update own profile (display_name, password, email). Changing the password or email requires `current_password`; `is_superuser`, `is_active` and `is_verified` are ignored |

> The admin panel uses `/admin/users/*` for user management because those routes carry first-class behaviors: auto-force-logout-on-block, suspension emails, audit logging, and full data cleanup (Postgres rows, Weaviate tenant, on-disk files) on delete.

### RAG (`/rag/*`)

Per-user document indexing and retrieval. Every endpoint operates on the authenticated user's Weaviate tenant — strict isolation, no cross-user leakage.

| Method | Path                            | Purpose                                                  |
|--------|---------------------------------|----------------------------------------------------------|
| POST   | `/rag/query`                    | Single-shot RAG Q&A with citations. Merges retrieval from personal docs + shared knowledge base. Returns `{answer, sources[], latency_ms}`. Optional `session_id` saves the turn to that chat |
| GET    | `/rag/documents`                | List the authenticated user's indexed documents          |
| POST   | `/rag/documents`                | Upload + index a document (PDF, TXT, MD, DOCX; 10MB cap) into the user's tenant. Re-uploading a file name replaces its chunks; the response says how many were replaced |
| DELETE | `/rag/documents/{filename}`     | Remove a document from the user's tenant                 |
| POST   | `/rag/reindex`                  | Re-index every file in the user's docs folder (useful after embedding model changes) |

**Honest notes:**
- `/rag/query` always queries **both** personal docs and the shared knowledge base in a merged top-k retrieval. Source objects carry an `origin` field (`"personal"` or `"knowledge_base"`) so the UI can render distinct badges. This is different from the agent flow, where the LLM picks per-turn whether to call `document_search` or `knowledge_base_search`.
- Name matching for replace/delete is exact (Weaviate tokenizes file names by word, so near matches such as `a.txt` / `b.txt` are filtered out).
- Reindex is needed when changing `EMBEDDING_MODEL` — existing vectors are locked at the dimension they were created with; the model swap requires dropping collections and re-ingesting.

### Agent (`/agent/*`)

Multi-turn conversational agent with 10 tools, streaming, session persistence, and multi-LLM ensemble.

| Method | Path                                          | Purpose                                                  |
|--------|-----------------------------------------------|----------------------------------------------------------|
| POST   | `/agent/chat`                                 | Multi-turn agent with tools + memory (non-streaming). Returns the final synthesized answer plus source metadata |
| POST   | `/agent/stream`                               | Streaming agent via Server-Sent Events. Emits live tool-call events (`running` → `done`), token deltas, and source attachments as they happen |
| POST   | `/agent/ensemble`                             | Multi-LLM consensus mode. Fans the query out to N models in parallel, judge ranks + synthesizes the final answer. Optional `session_id` saves the question and the verdict to that chat |
| GET    | `/agent/sessions`                             | List the authenticated user's chat sessions (auto-titled, sorted by recency) |
| GET    | `/agent/sessions/{session_id}/messages`       | Full message history for one session, with each assistant message's saved `metadata` (mode, sources, tool calls, latency) |
| POST   | `/agent/sessions/{session_id}`                | Create a session with a specific UUID (idempotent — used by frontend to anchor a session before the first user message) |
| PATCH  | `/agent/sessions/{session_id}`                | Rename a session (override the auto-generated title)     |
| DELETE | `/agent/sessions/{session_id}`                | Delete a session and all its messages                    |

**SSE event shape on `/agent/stream`:**
The stream emits `data:` lines carrying JSON events of types `token` (partial assistant content), `tool_start` (tool call started, with name + args), `tool_end` (tool call finished with output preview), `done` (terminal event carrying the final answer, sources, and tool-call summary), and `error`.

### Voice (`/voice/*`)

Speech-to-text via faster-whisper, text-to-speech via Edge or Piper.

| Method | Path                            | Purpose                                                  |
|--------|---------------------------------|----------------------------------------------------------|
| POST   | `/voice/transcribe`             | Audio → text. Multipart upload (WAV/MP3/M4A/OGG); returns transcript + detected language |
| POST   | `/voice/tts`                    | Text → audio. JSON body with text + language; returns audio bytes in the configured TTS format |

The TTS engine is configurable via `TTS_BACKEND` (`edge` = Microsoft neural voices online, 37 languages; `piper` = local offline voices). Edge auto-picks the matching native voice for the language code. Input text is normalized first (markdown removed, CJK/full-width punctuation handled) so non-Latin scripts synthesize without errors.

### Attachments (`/attachments/*`)

Document and image extraction utility — used by the chat composer for "drag & drop a file" before sending it as context.

| Method | Path                            | Purpose                                                  |
|--------|---------------------------------|----------------------------------------------------------|
| POST   | `/attachments/extract`          | PDF/image → text. Tries text extraction first, falls back to a provider-aware vision model (Llama-4 Scout on Groq, Llama-3.2-Vision on OpenRouter, or local `llama3.2-vision` on Ollama) for scanned PDFs and image content. Returns the extracted text, method, and char count; a vision model that returns no text surfaces as a `503` rather than a silent empty result |

### Admin (`/admin/*`)

User management, knowledge base curation, and system stats. Gated by role:
- `super_admin` — all admin endpoints
- `corpus_admin` — only `/admin/corpus/*` endpoints
- All others — `403 Forbidden`

#### User management (`super_admin` only)

| Method | Path                                      | Purpose                                                  |
|--------|-------------------------------------------|----------------------------------------------------------|
| GET    | `/admin/users`                            | List all users with role, active status, verification status, created_at |
| PATCH  | `/admin/users/{user_id}/role`             | Change user's role. Self-protection: super_admins cannot demote themselves. Auto-syncs `is_superuser` flag with role |
| PATCH  | `/admin/users/{user_id}/active`           | Suspend or unblock a user. On block: sets `is_active=false` AND `jwt_invalidated_at=now()` atomically (immediate force-logout), fires "account suspended" email with optional reason. On unblock: fires "account restored" email |
| PATCH  | `/admin/users/{user_id}`                  | Edit user display name. Email is intentionally not editable (login identity) |
| POST   | `/admin/users/{user_id}/send-reset`       | Trigger password reset flow for a target user. Reuses fastapi-users forgot_password flow, fires reset email |
| POST   | `/admin/users/{user_id}/force-logout`     | Set `jwt_invalidated_at=now()` for the target user, invalidating every JWT issued before this moment. The user is rejected with `401` on their very next request. Self-protection: admins cannot force-logout themselves |

#### Knowledge base management (`corpus_admin` or higher)

| Method | Path                                      | Purpose                                                  |
|--------|-------------------------------------------|----------------------------------------------------------|
| POST   | `/admin/corpus/ingest`                    | Structured JSON ingest into the shared `GlobalKnowledgeBase` Weaviate collection. Each item carries explicit metadata (text, content_type, source_title, author, language, etc.) — use this path when you want fine-grained control over per-chunk attributes |
| POST   | `/admin/corpus/upload`                    | File upload into the shared KB (PDF, TXT, MD, DOCX). 25MB cap. The file is chunked with the same loaders as personal RAG, then embedded + inserted. Form fields: `file`, `content_type`, `source_title`, `author` |
| GET    | `/admin/corpus/stats`                     | Total chunk count in the shared KB                       |
| GET    | `/admin/corpus/sources`                   | List all sources in the KB, grouped by `source_title`, with per-source chunk counts and content_type. Sorted most-chunks-first |
| DELETE | `/admin/corpus/sources?source_title=X`    | Delete every chunk whose source_title matches exactly. Source title comes as a query parameter (not path segment) because titles can contain arbitrary punctuation. Returns `{source_title, deleted}` |
| POST   | `/admin/corpus/search`                    | Hybrid search preview over the KB (BM25 + vector blend, configurable alpha 0.0–1.0). Admin-facing sanity check before users see results — the same `global_search` function used by the agent's `knowledge_base_search` tool |

#### System stats (`super_admin` only)

| Method | Path                            | Purpose                                                  |
|--------|---------------------------------|----------------------------------------------------------|
| GET    | `/admin/stats`                  | High-level dashboard stats: `total_users`, `corpus_total` (KB chunk count) |

### Default (`/`)

| Method | Path                            | Purpose                                                  |
|--------|---------------------------------|----------------------------------------------------------|
| GET    | `/health`                       | Public health check. Returns `{status, version, provider, model, embedding_model, voice_enabled, tts_backend}`. Used by Docker healthchecks and ops monitoring |
| GET    | `/health/live`                  | Liveness probe: the process is up. Checks nothing external, so a database blip never triggers restarts |
| GET    | `/health/ready`                 | Readiness probe: checks Postgres (required) and Redis/Weaviate (reported, degrade only). `503` when Postgres is down |
| GET    | `/`                             | Public service root. Returns a self-description listing main endpoint paths — useful for discovering the API surface from a curl |

---

### Authentication recap by endpoint group

| Group           | Auth required?                                                                    |
|-----------------|-----------------------------------------------------------------------------------|
| `/auth/*`       | Public (these issue auth, they don't consume it)                                  |
| `/users/me`     | Any authenticated user                                                            |
| `/rag/*`        | Any authenticated user                                                            |
| `/agent/*`      | Any authenticated user                                                            |
| `/voice/*`      | Any authenticated user                                                            |
| `/attachments/*`| Any authenticated user                                                            |
| `/admin/users/*`, `/admin/stats` | `super_admin`                                                    |
| `/admin/corpus/*` | `corpus_admin` or `super_admin`                                                 |
| `/health*`, `/` | Public                                                                            |

Every authenticated endpoint runs the JWT-freshness check against `users.jwt_invalidated_at`, so force-logout is enforced globally — chat, RAG, voice, attachments, sessions, admin. There is no authenticated route that lets a force-logged-out token survive.

## Testing

```bash
pip install -r requirements-dev.txt   # pytest + ruff (and the runtime requirements)
pytest
```

Tests cover the calculator (including malicious-input rejection), schema validation, memory eviction, tool argument parsing, the tool-call de-duplication logic, authentication flows, and the security layer (upload signature sniffing, rate-limit keying, the Sentry DSN guard, the secrets loader, and security headers — see `tests/test_security.py`). Most tests need no external services. `tests/integration/` (tenant isolation, replace-on-re-upload) runs against a real Weaviate with a fake embedder and is skipped when none is reachable: start one with `docker compose -f docker/docker-compose.yml up -d weaviate` (set `WEAVIATE_URL=http://localhost:8080` if `.env` uses the Docker hostname). CI starts one automatically and also runs `ruff` and ESLint as blocking checks. `python scripts/smoke_test.py` checks a running stack end to end (signup, login, chat).

For RAG quality evaluation:

```bash
pip install -r requirements-eval.txt
python evals/ragas_eval.py
```

Outputs faithfulness, answer relevancy, context precision, and context recall.

---

## Trade-offs and design notes

- **LangGraph over LangChain agents.** Explicit state transitions make streaming, debugging, and testing dramatically easier. Trying to stream from a LangChain `AgentExecutor` was painful; LangGraph emits `updates` and `messages` events you can directly forward over SSE.
- **Weaviate over Chroma.** Multi-tenancy is a first-class feature in Weaviate — each user gets a logically isolated tenant under one collection, instead of one collection per user. Cleaner ops, better resource sharing, real hybrid search (BM25 + vector) built in.
- **BGE-M3 over English-only embedding models.** A real differentiator for non-English use cases. The dimension cost (1024 vs 384) and the disk cost (~2.2GB vs ~130MB) is worth paying for cross-lingual retrieval that actually works on Urdu, Arabic, Hindi, Chinese, etc.
- **Provider abstraction with contextvar-based user isolation.** Every tool that touches user data reads `get_current_user()` instead of receiving a `user_id` parameter. Tool signatures stay clean for the LLM, accidental cross-user leakage is impossible, and the agent loop is trivially auditable.
- **Provider-aware vision, not a hardcoded model.** OCR routes to `active_vision_model`, which follows `LLM_PROVIDER` the same way the agent and ensemble models do. Switching providers repoints vision too — no separate config to keep in sync. Inputs are normalized to PNG first so formats like webp/gif work on every backend.
- **PostgreSQL + Alembic + fastapi-users.** Real multi-tenant data needs real relational guarantees and migration tooling. fastapi-users handles auth on top of SQLAlchemy and does the boring parts well, including OAuth account linking.
- **httpOnly cookies for browser, Bearer JWT for CLI.** Two transports, same JWT strategy. Browser clients are XSS-resistant; API clients still work with `Authorization` headers.
- **Custom JWT strategy with `iat` claim.** fastapi-users' default JWT doesn't include `iat`. We override `JWTStrategy.write_token` to add it so the freshness check (against `jwt_invalidated_at`) has a referent. Same security guarantees as the default, plus immediate revocation.
- **Force-logout enforced globally, not just on /admin.** First implementation gated only admin routes — meaning regular users could keep chatting after being force-logged-out. Fix: `current_active_user` itself runs the freshness check, so every authenticated endpoint enforces it.
- **Account suspension override at the `UserManager.authenticate` level.** Wrong-password attempts return `None` (generic bad creds). Correct password + inactive raises a custom exception that the global handler turns into a 403 with a clear message. This means probing emails with wrong passwords reveals nothing; only someone with the actual password learns that an account is suspended. Acceptable security tradeoff: the legitimate user finds out exactly when they need to.
- **Two separately-scoped retrieval tools.** `document_search` (personal-only) and `knowledge_base_search` (shared-only) deliberately do NOT overlap. A first design where both invoked the merged retrieval caused recursion loops because the agent oscillated between them. Lesson: when tools overlap semantically, LLMs thrash.
- **Runtime tool-call de-duplication.** A node wrapping the tool executor caches identical (name, args) calls and blocks a second single-shot retrieval call within one turn. Capable models rarely trigger it; weak local models would otherwise loop on the same search and, on CPU, turn a 4-second answer into a multi-minute spiral.
- **Language directive placed after history.** The response-language instruction is emitted for every language (including English) and injected as a system message *after* the conversation history, right before the user turn — so it outweighs the language of prior turns. This is what makes a mid-conversation switch actually take, even on weaker models.
- **SSE over WebSockets.** Simpler. One-way streaming is all we need. FastAPI's `StreamingResponse` handles it natively.
- **DuckDuckGo, not Google.** No API key. Trade-off is occasionally lower-quality results.
- **The agent gets retrieval as tools, not a prompt prefix.** The LLM decides per-turn whether documents are relevant and which corpus to query, instead of blindly retrieving on every message.
- **BGE-M3 pre-warm in FastAPI lifespan.** Without it, the first user request triggers a silent 2.2GB model download, looking like a hang. Pre-warming at startup surfaces the download in container logs and keeps the model in `lru_cache` for the container's life.
- **Lazy-loaded singletons** (Weaviate client, embeddings, LLM, Whisper model) cached with `lru_cache` so first request is slow but subsequent ones are fast.

---

## Honest limitations

I'd rather list these than have a recruiter find them:

- **CSV analysis and Python REPL are temporarily disabled.** Small open-source models hallucinate filenames and forget to wrap results in `print()`. The tools are still in the repo but unregistered. Rebuilding in Phase 5 with a persistent Jupyter-style kernel and a larger tool-calling model.
- **OpenRouter free tier is rate-limited.** Free-tier requests go into a low-priority queue upstream; under load, multi-LLM ensemble candidates, the judge, and vision OCR can time out or `503`. These now fail *cleanly* — clear error messages and graceful degradation to a best-candidate verdict — rather than crashing. The architecture is unchanged (`LLM_PROVIDER=openrouter` routes the whole app through OpenRouter), and a $5–10 credit removes the queue, making ensemble and vision reliable. In testing, all features (including vision OCR and a fully-judged ensemble) completed on the free tier when it wasn't throttled — just slower.
- **Ollama is CPU-bound on machines without a GPU.** Chat works; the multi-step agent and vision OCR are slow enough to be impractical on CPU-only hardware (a small model answers quickly but produces weak tool-calling; a larger, smarter model is accurate but can take minutes per turn). The tool-call de-duplication guard prevents weak models from spiraling, but raw generation speed is still hardware-limited. Use Groq or OpenRouter for agent-heavy or vision workloads; keep Ollama for local, private chat.
- **Strict language switching is prompt-enforced, not guaranteed.** The directive is sent every turn and placed last so it overrides conversation history. On capable models (Groq, paid OpenRouter) the selected language is honored reliably; on the weakest models it's greatly improved but can occasionally drift. A deterministic post-generation translate pass would close the gap entirely but isn't implemented — it wasn't needed for the primary path.
- **Prompt injection is mitigated, not solved.** Retrieved text and attachments are treated as data in the system prompt; an attachment cannot close its own delimiter block; and a `web_search` query that copies a stretch of the user's private documents or attachment (40+ characters, 12+ for Chinese/Japanese/Korean) or exceeds 200 characters is blocked, since that query is the one thing sent to a third party. The tools are read-only and `web_search` runs once per turn. It does not catch a reworded or compressed copy, and a persuaded model can still mislead the user in its answer; regulated deployments would want a content classifier on uploaded files.
- **LLM-as-judge bias in the ensemble.** The judge is biased toward verbose/confident answers. Mitigated by mixing model families but not eliminated.
- **Managed production infrastructure is the next milestone.** TLS (a Caddy auto-HTTPS overlay), file-based secrets, security headers, CORS lockdown, Redis-backed rate limiting, audit logging, blocking dependency scans and a CI pipeline (tests, lint, image builds) are now in place. No hosting platform has been chosen yet. What remains for a fully hardened production deploy is managed Postgres and Weaviate, object storage for uploads, automated backups, and orchestration (Kubernetes) beyond docker-compose.
- **No frontend in-flight kick on force-logout.** Force-logout is enforced server-side on the user's next request. If they're idle in the chat UI, the UI doesn't proactively boot them — the next click does. A WebSocket-pushed logout would close that gap but adds significant complexity.

---

## What I learned building this

A few things tutorials don't cover:

- **Multi-tenant isolation is easier with a contextvar than with explicit parameters.** Threading `user_id` through every LangChain call site is painful and error-prone. Setting it once in the agent entry point and reading it from `get_current_user()` in tools is small, auditable, and impossible to forget at the route layer.
- **Tool selection is a system-prompt problem, not a model problem.** Most "the agent picked the wrong tool" issues went away after rewriting tool descriptions to emphasize *when* to use each one, not just *what* it does. The same was true on the attachment path — the agent searched for a file whose text was already inline until the prompt explicitly said "answer from this content, don't look it up."
- **Tool semantic overlap causes recursion loops.** Two tools that retrieve from overlapping data sources make the agent thrash — it tries one, gets a hit, tries the other "to be sure," reformulates, retries. The fix isn't a higher recursion cap; it's making tool boundaries genuinely distinct (and adding a runtime dedup guard) so the agent doesn't see a choice where there shouldn't be one.
- **A "no-op" default can be a bug.** The response-language directive returned an empty string for English, on the assumption English needed no instruction. That silently broke mid-conversation switches *back* to English: with no directive, the model followed the language of the recent conversation history and kept replying in the previous language. Emitting an explicit English directive — and placing the language instruction *after* the history, as the last thing the model reads — made switches stick, even on weaker models. Position in the prompt is leverage.
- **Instrument before theorizing.** A persistent "I can't see the file" bug was chased through three wrong hypotheses (bad model name, webp-only failure, the frontend dropping text) before adding logging proved OCR had been working the whole time and the agent simply wasn't reading the extracted text. Reading logs beats reasoning from priors.
- **Streaming UX is the difference between "demo" and "product."** Users tolerate latency if they can see something happening. The live trace timeline shipped before any actual perf work, and it changed how the system felt.
- **Multi-LLM ensembling produces visibly better answers on judgment questions, not factual ones.** For "what year was X invented" three models give the same answer. For "should I hire a senior or two juniors with limited runway" they disagree productively — and a smaller model from a different family caught a budget constraint that two bigger Llamas missed. The judge picked it. That's the moment the architecture earned its compute.
- **Defensive tool schemas catch real production bugs.** Groq's strict schema validation rejects LLM-quoted numeric arguments (`amount: "2100000"` when schema declares `float`). Adding `value: float | int | str` plus a coercion block in `calculator`, `currency_converter`, and `unit_converter` fixed a class of intermittent failures. The same defensive instinct applied to ensemble: free-tier providers sometimes return a response with no `choices`, which threw a cryptic `'NoneType' object is not subscriptable` until a guard turned it into a clean, informative error.
- **Security defaults like "force-logout on /admin" are decorative if they don't apply everywhere.** First implementation of force-logout only ran the freshness check on admin routes. Regular users could keep chatting indefinitely after being force-logged-out. Defense-in-depth: every authenticated endpoint runs the check, or none of them do.
- **Embedding dimensions lock collections.** Swapping `bge-small-en-v1.5` (384-dim) for `bge-m3` (1024-dim) requires dropping every collection. Discovered this when adding multilingual support — a config change that *seemed* trivial turned out to require a data migration. Lesson: embedding model is part of the storage contract, not the application config.
- **Two SQLAlchemy engines are sometimes necessary.** A connection pool can't safely span event loops in asyncpg. The main FastAPI loop and the background titler loop each need their own.
- **CSS variables beat duplicating styles.** Light/dark theming with a single source of truth (theme tokens in `globals.css`) made the implementation small and fixes effortless. The first attempt — Tailwind `dark:` variants on every component — was 20× the code.

---

## Roadmap

**Recently shipped — security & hardening:** Redis-backed rate limiting, security headers + CORS lockdown, magic-byte upload validation, structured audit logging (auth events *and* admin actions), optional Sentry error tracking, opt-in email verification, file-based secret support, a Caddy TLS overlay for production, and blocking dependency scanning in CI. Details in [Security & hardening](#security--hardening).

What's next, ordered by priority:

1. **Managed production infrastructure.** Managed Postgres and Weaviate, object storage for uploaded files, automated backups, and automated deployment (CI already runs test → build → scan). Kubernetes manifests as an alternative to docker-compose.
2. **Rebuild `python_repl` and `csv_reader` with a persistent Jupyter-style kernel.** Faster (no subprocess boot per call), more reliable (state persists across calls), pair with a larger tool-calling model.
3. **Langfuse dashboards for admin panel.** The traces are already captured; surface them in the UI for super_admins.
4. **Ragas-based eval harness in CI.** Measure retrieval quality on every change to the RAG pipeline.
5. **Prompt-injection content classifier.** Run uploaded documents through a safety check before they enter the agent context (basic mitigations are in place; see Honest limitations).
6. **Per-tenant resource quotas.** Storage limits per user, message quotas per session.
7. **Runtime provider & model switching from the admin panel.** Switch the active LLM provider, its agent model, and the vision model live from the admin UI (super_admin only), backed by a Postgres-stored config with a test-before-apply check — no `.env` edit or restart. Embedding model stays fixed (changing it requires re-indexing all vectors).
8. **Audit log surface in the admin panel.** The events are now emitted as structured logs (logins, role changes, suspensions, force-logouts, KB modifications); the remaining work is surfacing them in the UI for super_admins.

---

## Credits

Built by [Munir Khan](https://www.linkedin.com/in/munirkhan-ai/) — connect on [LinkedIn](https://www.linkedin.com/in/munirkhan-ai/). If this helped you understand how to build a real GenAI platform end-to-end — or you're considering CloudNest for your own organization's AI workspace — a star on the [repo](https://github.com/Muhammad-Munir-Khan/cloudnest-ai) is appreciated.