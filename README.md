# AI Spend Guardrail

A self-hosted proxy that sits between your application and the Anthropic API to enforce spending budgets, track costs in real time, and surface optimization insights — with zero changes to your existing SDK calls beyond swapping the base URL.

## What it does

- **Proxy** — drop-in replacement for `https://api.anthropic.com`. Works with streaming and non-streaming requests.
- **Budget enforcement** — three modes per project:
  - `alert-only` — track and alert, never block
  - `visible-downgrade` — silently swap to a cheaper model when spend hits 80 % of budget
  - `hard-cap` — return HTTP 429 once the budget is exhausted
- **Spend tracking** — Redis (Upstash) for sub-millisecond real-time counters; Postgres for durable per-request history
- **Telegram alerts** — Markdown-formatted messages fire at 50 %, 80 %, and 100 % of budget (once per threshold per 24 h)
- **Usage Coach** — analytics derived entirely from the request log:
  - Top cost drivers by model
  - Context-bloat detection (growing input-token curves across consecutive calls)
  - Model-downgrade suggestions for short calls that don't need a flagship model
- **Multi-project** — each project gets its own proxy key (`sk-guard-…`); the real Anthropic key is Fernet-encrypted at rest and never logged
- **Dashboard** — Next.js frontend with spend charts, enforcement badges, key generation, and the coach panel

## Architecture

```
Your app  ──►  FastAPI proxy  ──►  Anthropic API
                   │
                   ├── Redis (real-time spend counters)
                   ├── Postgres (request log, projects, keys)
                   └── Telegram bot (threshold alerts)

Next.js dashboard  ──►  FastAPI /user/* routes  ──►  Supabase Auth (JWT)
```

## Stack

| Layer | Technology |
|---|---|
| Proxy / API | FastAPI + httpx (async, streaming-safe) |
| Database | PostgreSQL via asyncpg (Supabase or Neon) |
| Cache | Upstash Redis |
| Encryption | Python `cryptography` (Fernet) |
| Auth | Supabase JWT (user dashboard) + bearer token (admin) |
| Frontend | Next.js 14, TypeScript, Tailwind CSS |

## Getting started

### 1. Database

Run [`backend/schema.sql`](backend/schema.sql) against a Postgres database (Supabase free tier works).

### 2. Backend

```bash
cd backend
cp .env.example .env          # fill in your values
pip install -r requirements.txt
uvicorn main:app --reload
```

**Required env vars** (see [`backend/.env.example`](backend/.env.example)):

| Variable | Description |
|---|---|
| `DATABASE_URL` | Postgres connection string |
| `UPSTASH_REDIS_URL` | Upstash Redis REST URL |
| `UPSTASH_REDIS_TOKEN` | Upstash Redis token |
| `ENCRYPTION_KEY` | Fernet key — generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `ADMIN_SECRET` | Bearer token for `/admin/*` endpoints |
| `SUPABASE_JWT_SECRET` | From Supabase → Settings → API |
| `TELEGRAM_BOT_TOKEN` | From @BotFather (optional) |

### 3. Frontend

```bash
cd frontend
cp .env.local.example .env.local   # fill in your values
npm install
npm run dev
```

**Required env vars** (see [`frontend/.env.local.example`](frontend/.env.local.example)):

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon/public key |
| `NEXT_PUBLIC_API_URL` | Backend URL (e.g. `http://localhost:8000`) |

### 4. Create a project and key

```bash
# Create a project
curl -X POST http://localhost:8000/admin/projects \
  -H "Authorization: Bearer <ADMIN_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-agent",
    "budget_daily": 5.00,
    "enforcement_mode": "hard-cap"
  }'

# Generate a proxy key (stores your real key encrypted)
curl -X POST http://localhost:8000/admin/projects/<project_id>/keys \
  -H "Authorization: Bearer <ADMIN_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"provider_key": "sk-ant-..."}'
# → {"proxy_key": "sk-guard-...", "warning": "Save this key — it will not be shown again."}
```

### 5. Point your app at the proxy

```python
import anthropic

client = anthropic.Anthropic(
    api_key="sk-guard-...",               # your proxy key
    base_url="https://your-proxy.railway.app",
)
```

No other code changes needed. Streaming, tool use, and all other Anthropic features pass through transparently.

## API reference

### Admin endpoints (bearer token auth)

| Method | Path | Description |
|---|---|---|
| `POST` | `/admin/projects` | Create a project |
| `GET` | `/admin/projects` | List all projects |
| `PATCH` | `/admin/projects/:id` | Update project settings |
| `POST` | `/admin/projects/:id/keys` | Generate a proxy key |
| `GET` | `/admin/projects/:id/spend` | Current daily/monthly spend |

### User endpoints (Supabase JWT auth)

| Method | Path | Description |
|---|---|---|
| `GET` | `/user/projects` | List the caller's projects |
| `POST` | `/user/projects` | Create a project |
| `GET` | `/user/projects/:id` | Project details + live spend |
| `PATCH` | `/user/projects/:id` | Update project |
| `POST` | `/user/projects/:id/keys` | Generate proxy key |
| `GET` | `/user/projects/:id/spend/history` | Daily spend time-series |
| `GET` | `/user/projects/:id/coach` | Usage-coach insights |

### Proxy endpoint

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/messages` | Anthropic-compatible messages endpoint |

## Enforcement modes

| Mode | Behavior |
|---|---|
| `alert-only` | Spend is tracked and Telegram alerts fire, but requests are never blocked or modified |
| `visible-downgrade` | At ≥ 80 % budget: requests are silently re-routed to the cheapest available model in the same family |
| `hard-cap` | At 100 % budget: requests return `HTTP 429` with `"type": "budget_exceeded"` |

## Usage Coach

The coach derives all insights from the existing `requests` table — no extra storage.

**Top cost drivers** — ranks models by total spend over a configurable window (default 30 days).

**Context bloat** — flags when ≥ 65 % of consecutive calls show strictly growing input tokens with ≥ 10 % average growth per call. Estimates wasted spend and suggests fixes (sliding window, summarization).

**Model suggestions** — finds expensive-model calls under 2 000 total tokens and estimates savings if a cheaper model had been used, filtering to suggestions with ≥ 30 % projected savings.

## Deployment

The backend is a single `uvicorn` process with no background workers — suitable for Railway, Render, or any container host. Redis counters reset on their own TTL (daily / monthly keys expire automatically). For production, set `DATABASE_URL` to a pooled connection string (e.g. Supabase transaction mode on port 6543).

## License

MIT
