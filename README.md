# AI Spend Guardrail

A self-hosted proxy that sits between your application and the Anthropic API — enforcing budgets, tracking spend in real time, and surfacing optimisation insights. Zero changes to your existing code beyond swapping the base URL.

## The problem

AI API costs are invisible until the invoice arrives. There's no way to set a hard limit per project, no alert when a runaway agent loop burns through your budget, and no easy way to answer "which model and which workflow is costing the most?"

## What it does

**Drop-in proxy**
Point your Anthropic client at this proxy instead of `api.anthropic.com`. Streaming, tool use, and all other features pass through transparently.

```python
client = anthropic.Anthropic(
    api_key="sk-guard-...",
    base_url="https://your-proxy.railway.app",
)
# No other changes needed
```

**Budget enforcement — three modes**

| Mode | Behaviour |
|---|---|
| `alert-only` | Track and alert via Telegram, never block |
| `visible-downgrade` | At ≥ 80% budget: silently re-route to cheapest model in the same family |
| `hard-cap` | At 100% budget: return HTTP 429 with `"type": "budget_exceeded"` |

**Telegram alerts**
Fires at 50%, 80%, and 100% of budget — once per threshold per 24 hours, not on every request.

**Usage Coach**
Derived entirely from the existing request log — no extra storage:
- Top cost drivers by model over a configurable window
- Context bloat detection (flags when input tokens grow ≥ 10% per consecutive call)
- Model downgrade suggestions (finds expensive-model calls under 2 000 tokens, estimates savings)

**Multi-project, encrypted keys**
Each project gets its own proxy key (`sk-guard-…`). Real Anthropic keys are Fernet-encrypted at rest and never appear in logs.

## Architecture

```
Your app  ──►  FastAPI proxy  ──►  Anthropic API
                    │
                    ├── Upstash Redis  (real-time spend counters)
                    ├── PostgreSQL     (request log, projects, keys)
                    └── Telegram bot  (threshold alerts)

Next.js dashboard  ──►  FastAPI /user/* routes  ──►  Supabase Auth
```

**Why Redis + Postgres?**
Redis counters update in sub-millisecond on every request — fast enough to enforce budgets inline. Postgres stores the full request history for the coach analytics, which can afford a slower query.

## Stack

| Layer | Technology |
|---|---|
| Proxy / API | FastAPI + httpx (async, streaming-safe) |
| Database | PostgreSQL via asyncpg |
| Cache | Upstash Redis |
| Encryption | Python `cryptography` (Fernet) |
| Auth | Supabase JWT (dashboard) + bearer token (admin) |
| Frontend | Next.js 14, TypeScript, Tailwind CSS |

## Getting started

### 1. Database

```bash
psql $DATABASE_URL -f backend/schema.sql
```

### 2. Backend

```bash
cd backend
cp .env.example .env
pip install -r requirements.txt
uvicorn main:app --reload
```

### 3. Frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install && npm run dev
```

### 4. Create a project and generate a proxy key

```bash
curl -X POST http://localhost:8000/admin/projects \
  -H "Authorization: Bearer <ADMIN_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-agent", "budget_daily": 5.00, "enforcement_mode": "hard-cap"}'

curl -X POST http://localhost:8000/admin/projects/<id>/keys \
  -H "Authorization: Bearer <ADMIN_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"provider_key": "sk-ant-..."}'
# → {"proxy_key": "sk-guard-..."}
```

Full API reference is in the [README's API section](#api-reference) below.

## API reference

**Admin endpoints** (bearer token auth)

| Method | Path | Description |
|---|---|---|
| `POST` | `/admin/projects` | Create a project |
| `GET` | `/admin/projects` | List all projects |
| `PATCH` | `/admin/projects/:id` | Update settings |
| `POST` | `/admin/projects/:id/keys` | Generate proxy key |
| `GET` | `/admin/projects/:id/spend` | Current spend |

**User endpoints** (Supabase JWT auth)

| Method | Path | Description |
|---|---|---|
| `GET` | `/user/projects/:id` | Project details + live spend |
| `GET` | `/user/projects/:id/spend/history` | Daily spend time-series |
| `GET` | `/user/projects/:id/coach` | Usage-coach insights |
| `POST` | `/user/projects/:id/keys` | Generate proxy key |
