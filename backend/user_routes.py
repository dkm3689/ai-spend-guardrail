"""
User-scoped project endpoints consumed by the Next.js dashboard.
All routes require a valid Supabase JWT (Authorization: Bearer <token>).
"""
from __future__ import annotations

import asyncio
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth_middleware import get_current_user_id
from coach import get_context_bloat, get_model_suggestions, get_top_cost_drivers
from crypto import encrypt_key
from database import get_pool
from redis_client import get_spend

router = APIRouter(prefix="/api", tags=["user"])


# ── models ────────────────────────────────────────────────────────────────────

class ProjectBody(BaseModel):
    name: str
    budget_daily: float | None = None
    budget_monthly: float | None = None
    enforcement_mode: str = "alert-only"
    telegram_chat_id: str | None = None


class KeyBody(BaseModel):
    provider_key: str


# ── helpers ───────────────────────────────────────────────────────────────────

async def _assert_owns(conn, project_id: str, user_id: str):
    row = await conn.fetchrow(
        "SELECT id FROM projects WHERE id = $1 AND owner_id = $2",
        project_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("/projects")
async def list_projects(user_id: str = Depends(get_current_user_id)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, budget_daily, budget_monthly, enforcement_mode,
                   telegram_chat_id, created_at
            FROM projects WHERE owner_id = $1 ORDER BY created_at DESC
            """,
            user_id,
        )

    result = []
    for row in rows:
        daily_spend, monthly_spend = await get_spend(str(row["id"]))
        result.append({**dict(row), "daily_spend": daily_spend, "monthly_spend": monthly_spend})
    return result


@router.post("/projects", status_code=201)
async def create_project(body: ProjectBody, user_id: str = Depends(get_current_user_id)):
    _validate_mode(body.enforcement_mode)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO projects
              (name, owner_id, budget_daily, budget_monthly, enforcement_mode, telegram_chat_id)
            VALUES ($1,$2,$3,$4,$5,$6)
            RETURNING id, name, budget_daily, budget_monthly, enforcement_mode, created_at
            """,
            body.name, user_id, body.budget_daily, body.budget_monthly,
            body.enforcement_mode, body.telegram_chat_id,
        )
    return {**dict(row), "daily_spend": 0.0, "monthly_spend": 0.0}


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user_id: str = Depends(get_current_user_id)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_owns(conn, project_id, user_id)
        row = await conn.fetchrow(
            "SELECT * FROM projects WHERE id = $1", project_id
        )
    daily_spend, monthly_spend = await get_spend(project_id)
    return {**dict(row), "daily_spend": daily_spend, "monthly_spend": monthly_spend}


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: str, body: ProjectBody,
    user_id: str = Depends(get_current_user_id),
):
    _validate_mode(body.enforcement_mode)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_owns(conn, project_id, user_id)
        row = await conn.fetchrow(
            """
            UPDATE projects
            SET name=$1, budget_daily=$2, budget_monthly=$3,
                enforcement_mode=$4, telegram_chat_id=$5
            WHERE id=$6
            RETURNING id, name, budget_daily, budget_monthly, enforcement_mode
            """,
            body.name, body.budget_daily, body.budget_monthly,
            body.enforcement_mode, body.telegram_chat_id, project_id,
        )
    return dict(row)


@router.get("/projects/{project_id}/spend/history")
async def spend_history(
    project_id: str, days: int = 7,
    user_id: str = Depends(get_current_user_id),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_owns(conn, project_id, user_id)
        rows = await conn.fetch(
            """
            SELECT DATE(created_at) AS date, SUM(cost) AS cost
            FROM requests
            WHERE project_id = $1
              AND created_at > NOW() - ($2 * INTERVAL '1 day')
            GROUP BY 1 ORDER BY 1
            """,
            project_id, days,
        )
    return [{"date": str(r["date"]), "cost": float(r["cost"])} for r in rows]


@router.post("/projects/{project_id}/keys", status_code=201)
async def create_key(
    project_id: str, body: KeyBody,
    user_id: str = Depends(get_current_user_id),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_owns(conn, project_id, user_id)

    plain_key = f"sk-guard-{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
    encrypted = encrypt_key(body.provider_key)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO api_keys (project_id, key_hash, provider_key_encrypted) VALUES ($1,$2,$3)",
            project_id, key_hash, encrypted,
        )

    return {"proxy_key": plain_key, "warning": "Save this key — it will not be shown again."}


@router.get("/projects/{project_id}/requests")
async def list_requests(
    project_id: str, limit: int = 50,
    user_id: str = Depends(get_current_user_id),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_owns(conn, project_id, user_id)
        rows = await conn.fetch(
            """
            SELECT model, input_tokens, output_tokens, cost,
                   was_downgraded, was_blocked, created_at
            FROM requests WHERE project_id = $1
            ORDER BY created_at DESC LIMIT $2
            """,
            project_id, limit,
        )
    return [dict(r) for r in rows]


@router.get("/projects/{project_id}/coach")
async def coach_insights(
    project_id: str, days: int = 30,
    user_id: str = Depends(get_current_user_id),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _assert_owns(conn, project_id, user_id)

    top_drivers, bloat, suggestions = await asyncio.gather(
        get_top_cost_drivers(pool, project_id, days),
        get_context_bloat(pool, project_id),
        get_model_suggestions(pool, project_id, days),
    )
    return {"top_drivers": top_drivers, "context_bloat": bloat, "model_suggestions": suggestions}


def _validate_mode(mode: str):
    valid = {"alert-only", "visible-downgrade", "hard-cap"}
    if mode not in valid:
        raise HTTPException(status_code=400, detail=f"enforcement_mode must be one of {valid}")
