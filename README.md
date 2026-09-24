# TrackT — AI Spend Guardrail

**Stop getting surprised by AI API bills.**

TrackT is an open-source proxy that sits between your app and the Anthropic API — enforcing per-project budgets, tracking spend in real time, and surfacing cost optimisation insights in a live dashboard.

**Live demo → [trackt.vercel.app](https://frontend-roan-pi-41.vercel.app)**

---

## The Problem

Companies embedding Claude into their products have no way to:
- Set a hard spend limit per project or team
- Get alerted before a runaway agent loop burns the budget
- Answer "which model and which workflow is costing the most?"
- See cost per request, per day, per team

You find out at the end of the month when the invoice arrives.

---

## What TrackT Does

### Drop-in proxy — zero code changes
Point your Anthropic client at TrackT instead of `api.anthropic.com`. Streaming, tool use, and all features pass through transparently.

```python
# Before
client = anthropic.Anthropic(api_key="sk-ant-...")

# After — one line change
client = anthropic.Anthropic(
    api_key="sk-guard-...",   # proxy key from dashboard
    base_url="https://your-trackt-instance.com",
)
```

### Budget enforcement — three modes

| Mode | Behaviour |
|---|---|
| `alert-only` | Track and alert via Telegram, never block |
| `visible-downgrade` | At ≥ 80% budget — silently re-route to cheapest model in the same family |
| `hard-cap` | At 100% budget — return HTTP 429 with `budget_exceeded` |

### Real-time spend dashboard

- Per-project daily and monthly spend
- Spend history charts (7 / 14 / 30 days)
- Full request log with model, tokens, cost, and blocked status
- Budget progress bars with colour alerts at 80%+

### AI Usage Coach

Automatically derived from your request log — no extra config:
- **Top cost drivers** — which model and workflow costs the most
- **Context bloat detection** — flags when input tokens grow >10% per consecutive call
- **Model suggestions** — finds expensive-model calls under 2,000 tokens and estimates savings if switched to Haiku

### Telegram alerts

Fires at 80%, 90%, and 100% of budget — once per threshold, not on every request.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Agent Mode (recommended — key never leaves your server) │
│                                                          │
│  Your App → TrackT Agent (localhost)                     │
│                  │                                       │
│                  ├──→ TrackT Backend  (budget check)     │
│                  ├──→ Anthropic API   (direct call)      │
│                  └──→ TrackT Backend  (log spend)        │
└─────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│  Stored Mode                               │
│                                            │
│  Your App → TrackT Backend → Anthropic API │
│             (key encrypted at rest)        │
└────────────────────────────────────────────┘

TrackT Backend
  ├── Upstash Redis   (real-time spend counters — sub-ms)
  ├── PostgreSQL      (request log, projects, keys)
  └── Telegram bot    (threshold alerts)

Next.js Dashboard → FastAPI /api/* routes → Supabase Auth
```

**Why Redis + Postgres?**
Redis counters update in sub-milliseconds on every request — fast enough to enforce budgets inline. Postgres stores the full request history for coach analytics, which can afford a slower query.

---

## Stack

| Layer | Technology |
|---|---|
| Proxy / API | FastAPI + httpx (async, streaming-safe) |
| Database | PostgreSQL via asyncpg |
| Cache | Upstash Redis |
| Encryption | Python `cryptography` (Fernet AES-256) |
| Auth | Supabase ES256 JWT (JWKS verification) |
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Agent | Standalone Python script |

---

## Quick Start

### 1. Clone and set up the database

```bash
git clone https://github.com/TrackT1480/ai-spend-guardrail
cd ai-spend-guardrail
psql $DATABASE_URL -f backend/schema.sql
```

### 2. Start the backend

```bash
cd backend
cp .env.example .env   # fill in DATABASE_URL, REDIS_URL, SUPABASE_URL
pip install -r requirements.txt
uvicorn main:app --reload
```

### 3. Start the frontend

```bash
cd frontend
cp .env.local.example .env.local   # fill in API URL and Supabase keys
npm install && npm run dev
```

### 4. Create a project and generate a proxy key

```bash
# Create a project
curl -X POST http://localhost:8000/admin/projects \
  -H "x-admin-secret: YOUR_ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-agent", "budget_daily": 5.00, "enforcement_mode": "hard-cap"}'

# Generate a proxy key (agent mode — key stays on your machine)
curl -X POST http://localhost:8000/api/projects/<id>/keys \
  -H "Content-Type: application/json" \
  -d '{"key_mode": "agent"}'
# → {"proxy_key": "sk-guard-..."}
```

### 5. Start the agent

```bash
cd agent
ANTHROPIC_API_KEY=sk-ant-...
GUARDRAIL_PROJECT_KEY=sk-guard-...
GUARDRAIL_URL=http://localhost:8000
python agent.py
# Listening on :8002
```

### 6. Point your app at the agent

```python
client = anthropic.Anthropic(
    api_key="sk-guard-...",
    base_url="http://localhost:8002",
)
# Your Anthropic key never leaves your machine
```

---

## Testing Budget Enforcement

```bash
# Set a low budget in the dashboard, then run:
for i in $(seq 1 50); do
  echo -n "Call $i: "
  curl -s http://localhost:8002/v1/messages \
    -H "Content-Type: application/json" \
    -d '{"model":"claude-haiku-4-5-20251001","max_tokens":50,"messages":[{"role":"user","content":"Hello"}]}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin)
txt=d.get('content',[{}])[0].get('text','')
print(txt[:40] if txt else 'BLOCKED: '+str(d.get('detail','')))"
done
```

---

## Anthropic Model Pricing

| Model | Input (per M tokens) | Output (per M tokens) |
|---|---|---|
| claude-haiku-4-5 | $0.80 | $4.00 |
| claude-sonnet-5 | $3.00 | $15.00 |
| claude-opus-5 | $15.00 | $75.00 |

TrackT calculates cost per request in real time and accumulates it in Redis for inline budget enforcement.

---

## Environment Variables

### Backend
```
DATABASE_URL=postgresql://...          # Supabase pooler port 6543
REDIS_URL=rediss://...                 # Upstash Redis (TLS)
SUPABASE_URL=https://xxx.supabase.co  # For JWKS ES256 verification
ENCRYPTION_KEY=...                     # Fernet key for stored Anthropic keys
ADMIN_SECRET=...                       # Admin API bearer token
TELEGRAM_BOT_TOKEN=...                 # Optional — for alerts
```

### Frontend
```
NEXT_PUBLIC_API_URL=https://your-backend.com
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```

---

## API Reference

**Admin endpoints** (`x-admin-secret` header)

| Method | Path | Description |
|---|---|---|
| `POST` | `/admin/projects` | Create a project |
| `GET` | `/admin/projects` | List all projects |
| `PATCH` | `/admin/projects/:id` | Update settings |
| `POST` | `/admin/projects/:id/keys` | Generate proxy key |

**User endpoints** (Supabase JWT)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/projects` | List projects with live spend |
| `GET` | `/api/projects/:id` | Project details |
| `GET` | `/api/projects/:id/spend/history` | Daily spend time-series |
| `GET` | `/api/projects/:id/requests` | Full request log |
| `GET` | `/api/projects/:id/coach` | AI coach insights |
| `POST` | `/api/projects/:id/keys` | Generate proxy key |

**Agent endpoints** (proxy key)

| Method | Path | Description |
|---|---|---|
| `POST` | `/agent/check` | Budget check before Anthropic call |
| `POST` | `/agent/report` | Report usage after Anthropic call |
| `POST` | `/v1/messages` | Stored mode proxy (pass-through) |

---

## Roadmap

- [ ] OpenAI and Google Gemini support
- [ ] Per-user spend tracking within a project
- [ ] Slack alerts (alongside Telegram)
- [ ] Cost forecasting based on usage trends
- [ ] Team seats and role-based access

---

## License

MIT — free to use, self-host, and modify.

---

## Contributing

PRs welcome. Open an issue first for large changes.

---

Built with FastAPI, Next.js, Supabase, Upstash Redis, and Python.
