# CloudNest.ai — Next.js frontend

The web UI for the CloudNest.ai backend (`../app/`, FastAPI). Next.js 15 (App Router, all client components), React 19, Tailwind v4. It talks to the API over HTTP and Server-Sent Events and authenticates with the httpOnly `genai_auth` cookie.

## Features

- Streaming agent answers with a live tool-call trace (SSE), collapsible sources and tool panels
- Chat modes: Agent (tools + memory), RAG-only, and multi-LLM ensemble
- Per-user documents (PDF, TXT, MD, DOCX) with a document manager; shared knowledge-base citations shown with a distinct badge
- File attachments in the composer (images and scanned PDFs go through the backend's vision OCR)
- Voice input (MediaRecorder → `/voice/transcribe`) and spoken answers (`/voice/tts`)
- Response-language selector, light/dark theme
- Sessions list with rename and delete
- Auth pages: login, signup, forgot/reset password, email verification, Google/GitHub OAuth buttons
- Admin panel (`/admin`) for `super_admin` and `corpus_admin`: users, knowledge-base corpus, stats

## Run it

From the repository root, start the backend first (see the root README), then:

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000 (use localhost, not 127.0.0.1: the cookie is scoped to it in dev)
npm run lint       # ESLint, enforced in CI
npm run build      # type-checks and builds
```

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend base URL. A **build-time** value (inlined into the bundle and into the CSP `connect-src` in `next.config.ts`); Docker passes it as a build arg. |

There is no `.env.local.example`. To override locally, create `frontend/.env.local` with `NEXT_PUBLIC_API_URL=...`.

## Backend requirement: CORS

The backend must allow the frontend origin with credentials. Set `CORS_ORIGINS` in the root `.env` as a **JSON list** of exact origins (no wildcards), for example:

```
CORS_ORIGINS=["http://localhost:3000"]
```

Restart the backend after changing it. If requests from the browser fail, open the DevTools console: a CORS error names the rejected origin.

## Security headers

`next.config.ts` sends a Content-Security-Policy, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` (microphone for the app only) and HSTS on every response. Check them in a real browser after changing anything that loads external resources.

## File map

```
app/
  page.tsx            landing page
  chat/page.tsx       main chat UI
  login, signup, forgot-password, reset-password, verify-email/   auth pages
  admin/              admin panel (users, corpus, stats)
  layout.tsx, globals.css

components/           Sidebar, ChatList, ChatMessage, Composer, DocumentManager, AgentTrace,
                      SourcesPanel, ToolCallsPanel, EnsembleResponse, MarkdownContent, MicButton,
                      TTSButton, LanguageSelector, ThemeToggle, OAuthButtons, AuthProvider, ...

lib/
  api.ts              fetch wrappers (credentials: "include") + SSE generator
  auth.ts             login/signup/reset helpers
  redirect.ts         safeRedirectPath (validates the post-login ?next= target)
  types.ts, language.ts, theme.ts, utils.ts
```

## Notes

- The mic uses MediaRecorder; WebM/Opus is the default and `/voice/transcribe` handles it.
- Image and scanned-PDF OCR uses the vision model of the active `LLM_PROVIDER` (Groq, OpenRouter or Ollama), so that provider must be configured on the backend.
- Streaming uses SSE; if it fails, the chat page falls back to the non-streaming `/agent/chat`.
- A 401 from any API call redirects to `/login?next=...` (outside the public pages).
- No frontend test runner yet; the checks are `npm run lint` and `npm run build`.
