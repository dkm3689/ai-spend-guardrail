from __future__ import annotations

import hashlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from admin import router as admin_router
from agent_routes import router as agent_router
from user_routes import router as user_router
from crypto import decrypt_key
from database import close_pool, get_pool
from enforcement import EnforcementMode, Project
from proxy import handle_proxy_request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    logger.info("Database pool ready")
    yield
    await close_pool()


app = FastAPI(title="AI Spend Guardrail", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(agent_router)
app.include_router(user_router)


# ── project lookup ─────────────────────────────────────────────────────────────

async def _get_project_and_key(proxy_key: str) -> tuple[Project, str]:
    key_hash = hashlib.sha256(proxy_key.encode()).hexdigest()
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT p.id, p.name, p.budget_daily, p.budget_monthly,
                   p.enforcement_mode, p.telegram_chat_id,
                   k.key_mode, k.provider_key_encrypted
            FROM api_keys k
            JOIN projects p ON k.project_id = p.id
            WHERE k.key_hash = $1
            """,
            key_hash,
        )

    if not row:
        raise HTTPException(status_code=401, detail="Invalid proxy API key")
    if row["key_mode"] == "agent":
        raise HTTPException(
            status_code=403,
            detail=(
                "This key is configured for agent mode. "
                "Run the Guardrail Agent on your infrastructure and point your app at it."
            ),
        )

    project = Project(
        id=str(row["id"]),
        name=row["name"],
        budget_daily=float(row["budget_daily"]) if row["budget_daily"] else None,
        budget_monthly=float(row["budget_monthly"]) if row["budget_monthly"] else None,
        enforcement_mode=EnforcementMode(row["enforcement_mode"]),
        telegram_chat_id=row["telegram_chat_id"],
    )
    provider_key = decrypt_key(row["provider_key_encrypted"])
    return project, provider_key


# ── proxy endpoint ─────────────────────────────────────────────────────────────

@app.post("/v1/messages")
async def proxy_messages(request: Request):
    proxy_key = request.headers.get("x-api-key", "")
    if not proxy_key:
        raise HTTPException(status_code=401, detail="Missing x-api-key header")

    project, stored_key = await _get_project_and_key(proxy_key)

    # Pass-through mode: caller supplies their own key per-request; it is never stored.
    # Takes priority over any stored key so users can self-manage key rotation.
    provider_key = request.headers.get("x-provider-key") or stored_key
    if not provider_key:
        raise HTTPException(
            status_code=401,
            detail=(
                "No provider key available. Either store a key via POST /keys, "
                "or pass your Anthropic key in the x-provider-key request header."
            ),
        )

    body = await request.json()
    pool = await get_pool()
    return await handle_proxy_request(body, dict(request.headers), project, provider_key, pool)


# ── health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}
